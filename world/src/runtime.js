import { spawn } from 'node:child_process';
import { existsSync, readFileSync, mkdirSync, appendFileSync, statSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { StringDecoder } from 'node:string_decoder';
import { voicePath, BUILTIN } from './voices.js';
import { pythonJson } from './helpers.js';

// Shown to end users, not to repository maintainers: the portable installer and
// the in-app one-click deployment are the only supported setup paths.
export const DEPLOY_HINT='尚未完成语音部署：请在“模型部署检测”里点击“一键部署”。如果这台电脑没有核显，部署页会列出显卡，请选择独显后再次点击部署按钮。';

// Model/runtime installation belongs to this repository's setup-native script.
// This extension never imports or executes another World extension.
export class SoftVoiceRuntime {
  constructor({ cfg, log, dataDir }) {
    this.cfg = cfg; this.log = log;
    this.root = join(dataDir, 'soft-voice');
    mkdirSync(this.root, { recursive: true });
    this.pending = new Map(); this.seq = 0; this.generation = 0;
    this.history = [];
    this.stage('idle', '尚未启动');
  }
  profile() {
    const file = join(this.root, 'runtime-profile.json');
    if (!existsSync(file)) throw new Error(DEPLOY_HINT);
    const p = JSON.parse(readFileSync(file, 'utf8'));
    if (!p.python || !p.runtime || p.mode !== 'igpu') throw new Error('无效的核显运行配置');
    return { ...p, python: resolve(this.root, p.python), runtime: resolve(this.root, p.runtime) };
  }
  hasLocalFiles() {
    return this.deploymentStatus().installed;
  }
  deploymentStatus() {
    const url='https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest';
    let installed=false, problem='';
    try {
      const p=this.profile();
      if (!existsSync(p.python)) throw new Error('Python 运行环境缺失');
      const configFile=join(p.runtime,'native-runtime.json');
      const c=JSON.parse(readFileSync(configFile,'utf8'));
      for (const [key,label] of [['dll','推理引擎'],['model','Qwen3-TTS 模型'],['codec','音频解码模型']]) {
        if (!c[key] || !statSync(resolve(p.runtime,c[key])).isFile() || statSync(resolve(p.runtime,c[key])).size===0) throw new Error(label+'文件缺失');
      }
      if (c.speechOnly && !existsSync(join(p.runtime,'voice-features.json'))) throw new Error('固定音色特征缺失');
      installed=true;
    } catch(err) { problem=err.code==='ENOENT'?'模型、引擎或运行配置文件缺失':err.message; }
    const phase=this.state?.phase||'idle';
    const connected=installed && !!this.worker && ['ready','playing','synthesizing','buffering'].includes(phase);
    const loading=installed && (!!this.readyPromise || ['load_model','validate_model','prepare_voice','prepare_audio','check_memory'].includes(phase));
    const state=!installed?'missing':phase==='error'?'error':phase==='waiting_memory'?'waiting_memory':connected?'connected':loading?'loading':phase==='sleeping'?'sleeping':'installed';
    return {installed,connected,state,url,model:'Qwen3-TTS 0.6B Base Q8',
      detail:!installed?problem:state==='error'?(this.workerError||this.state.detail):this.state?.detail||'运行文件已就位',
      verification:connected?'启动校验已通过':'文件存在检查；完整校验在开启语音时执行'};
  }
  memoryPolicy() {
    try {
      const c=JSON.parse(readFileSync(join(this.profile().runtime,'native-runtime.json'),'utf8'));
      if(c.compactGraphs===true && c.kvContext===1024 && c.speechOnly?.format===1) {
        const selected=this.cfg?.deviceName||c.deviceName;
        const devices=(this.deviceInventory||[]).filter(d=>d.name===selected);
        const device=devices.length===1?devices[0]:this.deviceName===selected?{kind:this.deviceType,vendorId:this.deviceVendorId}:null;
        if(c.streamTextEmbedding===true && c.adaptiveKv===true && device?.kind==='discrete' && device.vendorId===0x10de) {
          return {minimumGiB:2.75,recoveryGiB:3.25,layout:'progressive-kv',deviceType:'discrete',deviceName:selected};
        }
        return c.streamTextEmbedding===true ? {minimumGiB:3,recoveryGiB:3.5,layout:'text-rows'} :
          {minimumGiB:3.25,recoveryGiB:3.75,layout:'compact'};
      }
    } catch { /* Unconfigured or older layouts retain their existing guard. */ }
    return {minimumGiB:4,recoveryGiB:4.5,layout:'standard'};
  }
  assertVoiceSupported(key) {
    const config = JSON.parse(readFileSync(join(this.profile().runtime, 'native-runtime.json'), 'utf8'));
    if (config.speechOnly && key !== BUILTIN) {
      throw new Error('当前是固定音色精简运行时。更换音色前请切回完整运行时；当前音色保持不变。');
    }
  }
  stage(phase, detail) { this.state = { phase, stage: phase, detail }; }
  status() {
    return { ...this.state, initializing: !!this.readyPromise, loadingSince:this.readyPromise ? this.loadingAt : null, workerPid: this.worker?.pid ?? null,
      engine: 'Qwen3-TTS 0.6B Base / Q8_0 / Vulkan GPU', voice: this.cfg.voiceId || BUILTIN,
      deviceName:this.deviceName||this.cfg.deviceName||null,deviceType:this.deviceType||null,engineVersion:this.engineVersion||null,availableDevices:this.deviceInventory||[],
      history: this.history, loadMs: this.loadMs ?? null, nativeSettings:this.nativeSettings??null,startupTimings:this.startupTimings??null,
      sampleRate: 24000, deployment:this.deploymentStatus(), processMemory:this.workerMemory ?? null, lastSpeech: this.lastSpeech ?? null, workerError: this.workerError ?? null,
      lastRequestFailure:this.lastRequestFailure??null };
  }
  record(text) {
    const file = join(this.root, 'worker.log');
    try {
      if (existsSync(file) && statSync(file).size > 2 * 1024 * 1024) renameSync(file, file + '.previous');
      appendFileSync(file, text);
    } catch { /* Logging must not interrupt playback. */ }
  }
  async devices() {const p=this.profile();const result=await pythonJson(p,'coopanion_soft_voice.cli',['--runtime',p.runtime,'devices']);this.deviceInventory=result.devices;return result;}
  async prepare() { if (!this.hasLocalFiles()) throw new Error(DEPLOY_HINT); }
  async ensure() {
    if (this.stopPromise) await this.stopPromise;
    if (this.readyPromise) return this.readyPromise;
    if (this.worker && this.state.phase === 'sleeping') {
      this.loadingAt=Date.now(); this.stage('load_model','正在从低占用休眠唤醒');
      this.readyPromise=this.command('wake','__ready__',120000).finally(()=>{this.readyPromise=null;});
      return this.readyPromise;
    }
    if (this.worker && this.state.phase !== 'error') return;
    if (this.worker) await this.stop();
    this.readyPromise = this.startWorker().finally(() => { this.readyPromise = null; });
    return this.readyPromise;
  }
  async startWorker() {
    const p = this.profile(), generation = this.generation;
    this.loadingAt = Date.now();
    this.workerError = null; this.stage('load_model', '加载所选音色并预热');
    const pack = voicePath(this.root, this.cfg.voiceId || BUILTIN);
    const child = spawn(p.python, ['-m', 'coopanion_soft_voice.cli', '--runtime', p.runtime, 'worker', '--mode', 'igpu', ...(pack ? ['--voice-pack', pack] : []), ...(this.cfg.deviceName ? ['--device-name',this.cfg.deviceName] : [])],
      { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1', HF_HUB_OFFLINE: '1' } });
    this.worker = child;
    const stdout = new StringDecoder('utf8'), stderr = new StringDecoder('utf8');
    let carry = '', errorTail = '';
    const ready = new Promise((resolve, reject) => this.pending.set('__ready__', { resolve, reject }));
    child.stdout.on('data', bytes => {
      if (generation !== this.generation) return;
      carry += stdout.write(bytes);
      const lines = carry.split(/\r?\n/); carry = lines.pop() || '';
      for (const line of lines) {
        // Compatibility with the Python engine wire format, not an old-plugin dependency.
        if (!line.startsWith('@@COSY@@')) continue;
        try { this.message(JSON.parse(line.slice(8))); }
        catch (err) { this.fail(err); }
      }
    });
    child.stderr.on('data', bytes => {
      const text = stderr.write(bytes); errorTail = (errorTail + text).slice(-12000); this.record(text);
    });
    child.once('error', err => { if (generation === this.generation) this.fail(err); });
    child.once('close', code => {
      if (generation !== this.generation) return;
      this.worker = null;
      this.fail(new Error(errorTail.trim() || `语音进程退出 (${code})`),'worker_exit');
    });
    const timer = setTimeout(() => { this.fail(new Error('语音预热超过 120 秒'),'startup_timeout'); void this.terminateWorker(child).catch(err=>this.fail(err)); }, 120000);
    try { await ready; }
    catch (err) { await this.terminateWorker(child); throw err; }
    finally { clearTimeout(timer); }
  }
  diagnostic(event) {
    try { this.onDiagnosticEvent?.(event); } catch { /* Report failure never interrupts speech. */ }
  }
  fail(err,code='worker_error') {
    if(code)this.diagnostic({code:/GiB free RAM|keeping text only/.test(err.message)?'memory_guard':code});
    this.workerError = err.message; this.stage('error', err.message);
    for (const p of this.pending.values()) p.reject(err);
    this.pending.clear();
  }
  message(msg) {
    if(msg.processMemory) this.workerMemory=msg.processMemory;
    if(msg.nativeSettings) this.nativeSettings=msg.nativeSettings;
    if(msg.type==='ready') {this.deviceName=msg.device;this.deviceType=msg.deviceType;this.deviceVendorId=msg.deviceVendorId;this.engineVersion=msg.engineVersion;this.nativeSettings=msg.nativeSettings;this.startupTimings=msg.startupTimings;}
    if (msg.type === 'slept') {
      const p=this.pending.get('__sleep__'); this.pending.delete('__sleep__');
      this.stage('sleeping','低占用休眠：保留进程与播放器，模型已释放。'); p?.resolve(msg); return;
    }
    if (msg.type === 'status') {
      this.stage(msg.stage, msg.detail);
      if (msg.stage === 'playing' && msg.id) {
        const p = this.pending.get(msg.id);
        this.lastSpeech = { id: msg.id, synthesisMs: msg.synthesisMs, queueWaitMs: p?.queueWaitMs ?? 0,
          startDelayMs: p?.receivedAt ? Date.now() - p.receivedAt : null };
      }
    } else if (msg.type === 'ready' || msg.type === 'done') {
      const key = msg.type === 'ready' ? '__ready__' : msg.id;
      const p = this.pending.get(key); this.pending.delete(key);
      if (msg.type === 'ready') this.loadMs = Date.now() - this.loadingAt;
      if (msg.type === 'done') {
        this.lastSpeech = { ...this.lastSpeech, ...msg, at: Date.now() };
        this.lastSpeech.totalStartMs = (this.lastSpeech.queueWaitMs || 0) + (msg.firstDeviceCallbackMs ?? msg.firstChunkMs ?? 0);
        this.history ??= [];
        this.diagnostic({type:'playback',seconds:msg.seconds,realTimeFactor:msg.realTimeFactor,totalSynthesisMs:msg.totalSynthesisMs,underrunMs:msg.underrunMs,deviceUnderflows:msg.deviceUnderflows});
        this.history.push({ ...this.lastSpeech }); if (this.history.length > 30) this.history.shift();
      }
      this.stage('ready', '所选音色已就绪'); p?.resolve(msg);
    } else if (msg.type === 'error') {
      // A bounded utterance can fail while the native worker remains healthy.
      // Never replay partially heard audio or reject unrelated pending requests.
      if(msg.errorCode==='generation_limit' && msg.recoverable===true && msg.id && this.pending.has(msg.id)) {
        const pending=this.pending.get(msg.id);this.pending.delete(msg.id);
        const detail='上一段朗读达到生成上限，未完整读完；已跳过，后续消息可继续朗读。';
        this.lastRequestFailure={code:'generation_limit',at:Date.now(),detail};
        const error=Object.assign(new Error(detail),{code:'generation_limit',recoverable:true});
        this.workerError=null;this.stage('ready',detail);
        this.diagnostic({code:'generation_limit'});pending.reject(error);
      } else this.fail(new Error(msg.error || '语音合成失败'),msg.errorCode==='memory_guard'?'memory_guard':'worker_error');
    }
  }
  async speak(text, { receivedAt = Date.now() } = {}) {
    await this.ensure();
    if (!this.worker?.stdin?.writable) throw new Error('语音进程不可用');
    const id = 's' + (++this.seq);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.fail(new Error('语音生成或播放超时，请恢复语音'),'speech_timeout'); void this.terminateWorker(this.worker).catch(err=>this.fail(err)); }, 180000);
      this.pending.set(id, { resolve: result => { clearTimeout(timer); resolve(result); },
        reject: err => { clearTimeout(timer); reject(err); }, receivedAt, queueWaitMs: Date.now() - receivedAt });
      this.worker.stdin.write(JSON.stringify({ id, text, speed: 1, volume: this.cfg.volume, playbackMode:this.cfg.playbackMode||'auto',cacheRepeated:this.cfg.cacheRepeated!==false }) + '\n', err => { if (err) this.fail(err); });
    });
  }
  async openFolder() { spawn('explorer.exe', [this.root], { windowsHide: true, detached: true, stdio: 'ignore' }).unref(); return this.root; }
  async command(type,key,timeout) {
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.fail(new Error('语音休眠/唤醒超时'));void this.terminateWorker(this.worker).catch(err=>this.fail(err));},timeout);
      this.pending.set(key,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});
      this.worker?.stdin.write(JSON.stringify({type})+'\n',e=>{if(e)this.fail(e);});
    });
  }
  async sleep() {
    if (!this.worker || this.pending.size || this.state.phase!=='ready') throw new Error('当前语音忙，暂不能休眠');
    this.stage('suspending','正在释放模型，保留播放器与进程');
    await this.command('sleep','__sleep__',15000);
  }
  async terminateWorker(child) {
    if (!child || child.exitCode != null || child.signalCode != null) return;
    if (child.termination) return child.termination;
    child.termination = new Promise((done,reject) => {
      const closed=()=>{clearTimeout(timer);done();};
      const timer = setTimeout(()=>{child.removeListener('close',closed);reject(new Error('旧语音进程仍未退出，已阻止加载第二个模型；请重试停止'));},5000);
      child.once('close',closed);
      if (process.platform === 'win32') {
        const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
        killer.once('error', () => child.kill());
      } else child.kill();
    }).finally(()=>{child.termination=null;});
    return child.termination;
  }
  async stop() {
    if(this.stopPromise)return this.stopPromise;
    this.stopPromise=this.stopWorker().finally(()=>{this.stopPromise=null;});
    return this.stopPromise;
  }
  async stopWorker() {
    ++this.generation;
    const child = this.worker;
    this.fail(new Error('语音已停止'),null);
    this.stage('stopping','正在停止并释放语音模型');
    try {await this.terminateWorker(child);}
    catch(err){this.fail(err);throw err;}
    if(this.worker===child)this.worker=null;
    this.workerMemory=null;this.workerError=null;
    this.stage('stopped', '已停止并释放模型');
  }
}
