import { spawn } from 'node:child_process';
import { existsSync, readFileSync, mkdirSync, appendFileSync, statSync, renameSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { StringDecoder } from 'node:string_decoder';
import { voicePath, BUILTIN } from './voices.js';

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
    if (!existsSync(file)) throw new Error('请先运行仓库 scripts/install_world.py 配置独立语音环境');
    const p = JSON.parse(readFileSync(file, 'utf8'));
    if (!p.python || !p.runtime || p.mode !== 'igpu') throw new Error('无效的核显运行配置');
    return { ...p, python: resolve(this.root, p.python), runtime: resolve(this.root, p.runtime) };
  }
  hasLocalFiles() {
    try { const p = this.profile(); return existsSync(p.python) && existsSync(join(p.runtime, 'native-runtime.json')); }
    catch { return false; }
  }
  assertVoiceSupported(key) {
    const config = JSON.parse(readFileSync(join(this.profile().runtime, 'native-runtime.json'), 'utf8'));
    if (config.speechOnly && key !== BUILTIN) {
      throw new Error('当前是固定音色精简运行时。更换音色前请切回完整运行时；当前音色保持不变。');
    }
  }
  stage(phase, detail) { this.state = { phase, stage: phase, detail }; }
  status() {
    return { ...this.state, initializing: !!this.readyPromise, workerPid: this.worker?.pid ?? null,
      engine: 'Qwen3-TTS 0.6B Base / Q8_0 / Vulkan 核显', voice: this.cfg.voiceId || BUILTIN,
      history: this.history, loadMs: this.loadMs ?? null,
      sampleRate: 24000, lastSpeech: this.lastSpeech ?? null, workerError: this.workerError ?? null };
  }
  record(text) {
    const file = join(this.root, 'worker.log');
    try {
      if (existsSync(file) && statSync(file).size > 2 * 1024 * 1024) renameSync(file, file + '.previous');
      appendFileSync(file, text);
    } catch { /* Logging must not interrupt playback. */ }
  }
  async prepare() { if (!this.hasLocalFiles()) throw new Error('运行环境未安装，请运行 setup-native.ps1 和 install_world.py'); }
  async ensure() {
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
    const child = spawn(p.python, ['-m', 'coopanion_soft_voice.cli', '--runtime', p.runtime, 'worker', '--mode', 'igpu', ...(pack ? ['--voice-pack', pack] : [])],
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
      this.fail(new Error(errorTail.trim() || `语音进程退出 (${code})`));
    });
    const timer = setTimeout(() => { this.fail(new Error('语音预热超过 120 秒')); void this.terminateWorker(child); }, 120000);
    try { await ready; }
    catch (err) { await this.terminateWorker(child); throw err; }
    finally { clearTimeout(timer); }
  }
  fail(err) {
    this.workerError = err.message; this.stage('error', err.message);
    for (const p of this.pending.values()) p.reject(err);
    this.pending.clear();
  }
  message(msg) {
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
        this.history.push({ ...this.lastSpeech }); if (this.history.length > 30) this.history.shift();
      }
      this.stage('ready', '所选音色已就绪'); p?.resolve(msg);
    } else if (msg.type === 'error') this.fail(new Error(msg.error || '语音合成失败'));
  }
  async speak(text, { receivedAt = Date.now() } = {}) {
    await this.ensure();
    if (!this.worker?.stdin?.writable) throw new Error('语音进程不可用');
    const id = 's' + (++this.seq);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.fail(new Error('语音生成或播放超时，请恢复语音')); void this.terminateWorker(this.worker); }, 180000);
      this.pending.set(id, { resolve: result => { clearTimeout(timer); resolve(result); },
        reject: err => { clearTimeout(timer); reject(err); }, receivedAt, queueWaitMs: Date.now() - receivedAt });
      this.worker.stdin.write(JSON.stringify({ id, text, speed: 1, volume: this.cfg.volume }) + '\n', err => { if (err) this.fail(err); });
    });
  }
  async openFolder() { spawn('explorer.exe', [this.root], { windowsHide: true, detached: true, stdio: 'ignore' }).unref(); return this.root; }
  async command(type,key,timeout) {
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.fail(new Error('语音休眠/唤醒超时'));void this.terminateWorker(this.worker);},timeout);
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
    if (!child || child.exitCode != null) return;
    if (child.termination) return child.termination;
    child.termination = new Promise(done => {
      const timer = setTimeout(done, 5000);
      child.once('close', () => { clearTimeout(timer); done(); });
      if (process.platform === 'win32') {
        const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
        killer.once('error', () => child.kill());
      } else child.kill();
    });
    return child.termination;
  }
  async stop() {
    ++this.generation;
    const child = this.worker; this.worker = null;
    this.fail(new Error('语音已停止'));
    await this.terminateWorker(child);
    this.stage('stopped', '已停止并释放模型');
  }
}
