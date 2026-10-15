import { freemem, totalmem } from 'node:os';
import { listVoices, voicePath, importVoice, TUTORIAL, BUILTIN } from './voices.js';
import { CONFIG_GROUP, DEFAULTS, ID, volumePercent, configValues, validateConfigPatch } from './config.js';
import { petSayFromEntry } from './parser.js';
import { rememberReply, restoreReplies, replyProgress } from './reply-receipts.js';
import { BubbleSpeechSync } from './bubble-sync.js';
import { installBubbleBridge } from './bubble-bridge.js';
import { ToolCallTailer } from './tailer.js';
import { SoftVoiceRuntime } from './runtime.js';
import { VoiceReports } from './reports.js';
import { VoiceUpdates } from './updates.js';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const LOADING_PHASES = new Set(['check_environment', 'installed', 'bootstrap_uv', 'bootstrap_python', 'create_venv',
  'bootstrap_source', 'bootstrap_matcha', 'install_torch', 'install_dependencies', 'preflight',
  'download_reference', 'check_memory', 'validate_model', 'download_model', 'load_model', 'prepare_voice', 'prepare_audio', 'stopping', 'synthesizing', 'buffering', 'playing']);

export class SoftVoiceWorld {
  constructor(opts) {
    this.id = ID;
    this.opts = { ...opts, cfg: { ...DEFAULTS, ...opts.cfg } };
    this.settings = {};
    this.host = null;
    this.timer = null;
    this.queue = [];
    this.dropped = 0;
    this.speaking = false;
    this.lastSeen = {};
    this.recentReplies = [];
    this.active = false;
    this.blocked = false;
    this.draining = null;
    this.runtime = null;
    this.tailer = null;
    this.accepting = false;
    this.initialization = null;
    this.skippedBeforeReady = 0;
    this.speechEnabled = false;
    this.togglePromise = null;
    this.lastActivity = Date.now();
    this.sleepPromise = null;
    this.bubbleSync = new BubbleSpeechSync(() => this.bubbleSyncStatus().active);
    this.removeBubbleBridge = null;
    this.nextUpdateCheck=Date.now()+30000;this.updatePolling=null;
  }

  envPromptVars() {
    // Catch the final receipt before a handoff rebuilds the system prefix.
    // Polling keeps the existing audio cursor: it never replays skipped history.
    try { this.tailer?.poll(); } catch (err) { this.host?.log.warn(`无法同步近期回复回执: ${err.message}`); }
    const phase = this.runtime?.status?.().phase;
    let state = '语音正在准备，暂不能保证发声。';
    if (!this.active || !this.speechEnabled) state = '语音已停用，目前只显示文字。';
    else if (volumePercent(this.opts.cfg.volume) === 0) state = '音量为零，当前静音，只显示文字。';
    else if (phase === 'waiting_memory') state = '可用内存不足，暂时只显示文字，等待恢复。';
    else if (this.blocked || phase === 'error') state = '语音暂时发生故障，目前不能保证发声。';
    else if (phase === 'waiting_user') state = '语音运行环境尚未配置完整，目前只显示文字。';
    else if (phase === 'sleeping') state = '语音省内存待机中，下一次 pet_say 会自动加载模型并朗读，首句需要额外等待。';
    else if (this.accepting) state = '语音已启用且已就绪，你已经可以开口说话；pet_say 的可朗读文字会自动合成并播放。';
    return { 'softVoice.state': state, 'softVoice.recentReplies': replyProgress(this.recentReplies) };
  }
  tools() { return []; }

  console() {
    const st = this.runtime?.status?.() ?? { phase: 'idle', detail: '未启动' };
    const lampState = st.phase === 'ready' ? 'online' : st.phase === 'error' ? 'error' : LOADING_PHASES.has(st.phase) ? 'loading' : 'offline';
    return {
      label: '轻核语音 · Qwen3-TTS 超轻量高速语音引擎',
      promptDocs: [{
        key: 'worlds.soft-voice.envPrompt',
        title: '轻核语音 · Qwen3-TTS 超轻量高速语音引擎环境提示词',
        description: '说明自动朗读能力与当前状态；由 Cortico 合入系统提示词。',
        path: fileURLToPath(new URL('./ENV_PROMPT.md', import.meta.url)),
        role: 'envPrompt',
        vars: [{ name: 'softVoice.state', description: '当前语音能力、静音或异常状态' },
          { name: 'softVoice.recentReplies', description: '近期已成功输出的回复与实际回执，防止交接后重答' }],
      }],
      lamps: [{ label: 'TTS', state: lampState, hint: st.detail ?? st.phase }],
      panels: [{ id: 'controls', title: '语音控制', description: '试听、静音、音量、释放内存和恢复。' }, { id: 'status', title: '运行状态', description: '引擎、音色、延迟和异常诊断。' },
        { id: 'config', title: '配置', description: '队列、过期丢弃和内存恢复。' },
        { id:'diagnostics',title:'日志与诊断',description:'性能、故障报告，导出 ZIP 与脱敏 Issue。' },
        { id: 'voices', title: '音色库', description: '选择音色、导入 ZIP 与制作教程。' }],
      invoke: async (panel, method, args = []) => {
        if (!['controls','status','config','voices','diagnostics'].includes(panel)) throw new Error('未知语音面板');
        if (method === 'state') return { ...this.status(), values: configValues(this.opts.cfg),
          memory: { freeGiB: freemem()/1024**3, totalGiB: totalmem()/1024**3, ...(this.runtime?.memoryPolicy?.() ?? {minimumGiB:4,recoveryGiB:4.5,layout:'standard'}) },
          voices: listVoices(this.runtime.root), selectedVoice: this.opts.cfg.voiceId || BUILTIN, tutorial: TUTORIAL };
        if(panel==='diagnostics') {
          if(this.updating)throw new Error('正在更新语音代码，请等待更新完成后采集报告');
          if(method==='refreshReports')return this.reports.refresh();
          if(method==='collectReport')return this.reports.run('collect',['--seconds',args[0]===60?'60':'0']);
          if(method==='reportDetail')return this.reports.call('detail',['--id',args[0]]);
          if(method==='exportReport')return this.reports.call('export',['--id',args[0]]);
          if(method==='submitReport') {
            if(args[1]!==true)throw new Error('请确认向 Asryto 仓库提交脱敏摘要与相关日志');
            return this.reports.run('submit',['--id',args[0],'--authorized']);
          }
          if(method==='save')return this.saveConfig(args[0]);
        }
        if (panel === 'voices') {
          if (method === 'import') return importVoice(this.runtime, args[0]);
          if (method === 'select') return this.selectVoice(args[0]);
        }
        if (panel === 'config' && method === 'save') return this.saveConfig(args[0]);
        if (panel === 'controls') {
          if (this.updating && !['state','devices'].includes(method)) throw new Error('正在更新语音代码，请等待更新完成');
          if (method === 'checkUpdate') return this.updates.run('check',this.opts.botDir?join(this.opts.botDir,'..','..','extensions'):undefined);
          if (method === 'applyUpdate') return this.applyUpdate();
          if (method === 'devices') return this.runtime.devices();
          if (method === 'selectDevice') return this.selectDevice(args[0]);
          if (method === 'save') return this.saveConfig(args[0]);
          if (method === 'enable' || method === 'recover') { if (!this.speechEnabled) return this.setSpeechEnabled(true); void this.initialize(false).catch(err => this.host?.log.warn(err.message)); return this.status(); }
          if (method === 'disable') return this.setSpeechEnabled(false);
          if (method === 'stop') { await this.setSpeechEnabled(false); return this.status(); }
          if (method === 'restartDesktop') {
            if(args[0]!==true)throw new Error('请先确认重启；未确认时保持当前运行。');
            if(this.updates?.status().busy)throw new Error('更新正在执行，请等待更新结束。');
            if(!this.updates?.status().requiresRestart)throw new Error('当前没有待重启的语音扩展更新。');
            if(!this.opts.requestDesktopRestart)throw new Error('当前宿主未提供重启入口，请手动重启桌宠。');
            return this.opts.requestDesktopRestart();
          }
          if (method === 'clearQueue') { for(const item of this.queue)this.bubbleSync.finish(item.key,'cancelled');this.queue.length = 0; return this.status(); }
          if (method === 'test') {
            if (this.switchingDevice || !this.accepting || this.blocked || this.speaking || this.queue.length) throw new Error('请等语音就绪且当前播放结束后再试听');
            this.speaking = true;
            try { await this.sleepPromise; await this.runtime.speak('我在这里陪你呀，慢慢来，不着急。', { receivedAt: Date.now() }); }
            finally { this.lastActivity = Date.now(); this.speaking = false; this.draining = this.drain(); }
            return this.status();
          }
          throw new Error('未知语音控制操作');
        }
        throw new Error('未知语音面板');
      },
    };
  }

  async start(host) {
    this.host = host;
    this.active = true;
    this.blocked = false;
    this.accepting = false;
    this.skippedBeforeReady = 0;
    this.runtime = this.makeRuntime(host);
    this.updates = new VoiceUpdates(this.runtime);
    this.reports = new VoiceReports(this.runtime,this.opts.cfg,host.log);
    this.runtime.onDiagnosticEvent=event=>this.reports.observe(event);
    this.settingsFile = join(this.runtime.root, 'settings.json');
    this.speechEnabled = false;
    if (existsSync(this.settingsFile)) {
      try {
        const savedSettings = JSON.parse(readFileSync(this.settingsFile, 'utf8'));
        if (!savedSettings || typeof savedSettings !== 'object' || Array.isArray(savedSettings)) throw new Error('配置文件格式无效');
        const savedConfig = savedSettings.config ? validateConfigPatch(savedSettings.config) : {};
        this.settings = savedSettings;
        this.speechEnabled = savedSettings.speechEnabled === true;
        if (!('lowPowerMode' in savedConfig)) savedConfig.lowPowerMode = (savedConfig.idleUnloadSec ?? 0) > 0 || (savedConfig.lowMemoryMiB ?? 0) > 0;
        Object.assign(this.opts.cfg, savedConfig);
        this.opts.cfg.voiceId = savedSettings.selectedVoice || this.opts.cfg.voiceId || BUILTIN;
      }
      catch (err) { host.log.warn(`无法读取语音开关，保持停用: ${err.message}`); }
    }
    this.cursorFile = join(this.runtime.root, 'cache', 'toolcall-cursor.json');
    let saved = null;
    if (existsSync(this.cursorFile)) {
      try { saved = JSON.parse(readFileSync(this.cursorFile, 'utf8')); this.lastSeen = saved.lastSeen || {}; this.recentReplies = restoreReplies(saved.recentReplies); }
      catch (err) { host.log.warn(`无法读取 TTS 游标: ${err.message}`); }
    }
    this.tailer = new ToolCallTailer(this.opts.dataDir, entry => this.onToolCall(entry), host.log,
      { checkpoint: cursor => this.saveCursor(cursor) });
    this.tick = () => {
      if(!this.updatePolling)this.updatePolling=this.maybeUpdates().catch(err=>host.log.warn(`自动更新：${err.message}`)).finally(()=>{this.updatePolling=null;});
      void this.maybeUnload().catch(err => host.log.warn(`空闲卸载失败: ${err.message}`));
      if (this.speechEnabled && this.active && !this.accepting && !this.initialization &&
          this.opts.cfg.autoRecover && this.runtime?.state?.phase === 'waiting_memory' && freemem() >= (this.runtime?.memoryPolicy?.().recoveryGiB ?? 4.5)*1024**3 &&
          Date.now() - (this.lastMemoryRetry || 0) >= 60000) {
        this.lastMemoryRetry = Date.now();
        void this.initialize(false).catch(err => host.log.warn(`内存恢复后语音重试：${err.message}`));
      }
      try { this.tailer?.poll(); } catch (err) { host.log.warn(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 监听失败: ${err.message}`); }
    };
    this.tick();
    this.timer = setInterval(this.tick, Math.max(80, Number(this.opts.cfg.pollMs) || 180));
    try { this.removeBubbleBridge = await installBubbleBridge(this); }
    catch(err) { host.log.warn(`气泡同步适配桥未启用: ${err.message}`); }
    // Activation never grants download permission, including legacy autoInstall=true.
    if (!this.speechEnabled) this.runtime.stage('disabled', '语音已停用；安装完成不代表启用。');
    else if (this.runtime.hasLocalFiles()) void this.initialize(false).catch(err => {
      host.log.warn(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 本机环境启动失败: ${err.message}`);
    });
    else this.runtime.stage('waiting_user', '运行环境未配置，请按独立扩展安装指南安装。');
  }

  makeRuntime(host) { return new SoftVoiceRuntime({ cfg: this.opts.cfg, log: host.log, dataDir: this.opts.dataDir }); }

  async maybeUpdates(now=Date.now()) {
    if(!this.active||!this.updates||!this.opts.cfg.autoCheckUpdates||this.updates.status().busy||this.updating||this.switchingDevice)return;
    if(now>=this.nextUpdateCheck){
      this.nextUpdateCheck=now+86400000;
      try{await this.updates.run('check',this.opts.botDir?join(this.opts.botDir,'..','..','extensions'):undefined);}
      catch(err){this.nextUpdateCheck=now+3600000;this.host?.log.warn(`自动检查失败，一小时后重试：${err.message}`);return;}
    }

  }

  async maybeUnload(now = Date.now(), freeMiB = freemem()/1024**2) {
    if (!this.opts.cfg.lowPowerMode) return;
    const seconds = this.opts.cfg.idleUnloadSec;
    const pressure = this.opts.cfg.lowMemoryMiB > 0 && freeMiB < this.opts.cfg.lowMemoryMiB;
    if ((!seconds && !pressure) || !this.active || !this.speechEnabled || !this.accepting || this.blocked ||
        this.speaking || this.queue.length || this.initialization || this.togglePromise || this.sleepPromise ||
        this.runtime?.status().phase !== 'ready' || (!pressure && now - this.lastActivity < seconds * 1000)) return;
    const runtime = this.runtime;
    this.sleepPromise = (async () => {
      if (this.opts.cfg.keepWorker) await runtime.sleep();
      else await runtime.stop();
      if (this.active && this.speechEnabled && this.runtime === runtime) {
        runtime.workerError = null;
        runtime.stage('sleeping', `${pressure?'内存保护触发：':''}${this.opts.cfg.keepWorker?'低占用休眠，保留进程与播放器':'深度休眠，进程已退出'}；模型已释放，下一句话自动唤醒。`);
      }
    })().finally(() => { this.sleepPromise = null; });
    await this.sleepPromise;
  }

  bubbleSyncStatus() {
    const enabled = !!this.opts.cfg.syncBubbles, available = !!this.removeBubbleBridge;
    const phase = !enabled ? 'disabled' : !this.active || !this.speechEnabled ? 'voice_off' :
      volumePercent(this.opts.cfg.volume) === 0 ? 'muted' : !available ? 'unavailable' :
      !this.accepting || this.blocked ? 'waiting_voice' : 'active';
    return { enabled, available, active: phase === 'active', phase };
  }

  status() {
    return { ...this.runtime.status(), queueLength: this.queue.length, speaking: this.speaking,
      diagnostics:this.reports?.status(),updates:this.updates?.status(),switchingDevice:!!(this.switchingDevice||this.deviceChecking),deviceChange:this.deviceChange||null,selectedDeviceName:this.opts.cfg.deviceName||'',updating:!!this.updating,
      bubbleSync: this.bubbleSyncStatus(),
      volume: volumePercent(this.opts.cfg.volume),
      speechEnabled: this.speechEnabled, toggling: !!this.togglePromise,
      dropped: this.dropped, accepting: this.accepting, skippedBeforeReady: this.skippedBeforeReady };
  }

  writeSettings(settings) {
    if (!this.settingsFile) throw new Error('轻核语音 · Qwen3-TTS 超轻量高速语音引擎 尚未启动');
    mkdirSync(dirname(this.settingsFile), { recursive: true });
    writeFileSync(this.settingsFile + '.tmp', JSON.stringify(settings), 'utf8');
    renameSync(this.settingsFile + '.tmp', this.settingsFile);
    this.settings = settings;
  }

  saveConfig(values) {
    const patch = validateConfigPatch(values);
    if ('deviceName' in patch && patch.deviceName!==this.opts.cfg.deviceName) throw new Error('请在语音控制的设备选择中切换，使模型安全重新加载');
    const next = { ...this.opts.cfg, ...patch };
    this.opts.persist?.(patch);
    this.writeSettings({ ...this.settings, speechEnabled: this.speechEnabled, config: configValues(next) });
    Object.assign(this.opts.cfg, patch);
    if (patch.syncBubbles === false) this.bubbleSync.cancelAll();
    if ((patch.lowPowerMode === false || (next.idleUnloadSec === 0 && next.lowMemoryMiB === 0)) && this.speechEnabled && (this.sleepPromise || this.runtime?.status().phase === 'sleeping')) {
      void Promise.resolve(this.sleepPromise).then(() => { if (this.active && this.speechEnabled && (!this.opts.cfg.lowPowerMode || (!this.opts.cfg.idleUnloadSec && !this.opts.cfg.lowMemoryMiB))) return this.initialize(false); }).catch(err => this.host?.log.warn(`恢复常驻失败: ${err.message}`));
    }
    if ('pollMs' in patch && this.timer) {
      clearInterval(this.timer);
      this.timer = setInterval(this.tick, this.opts.cfg.pollMs);
    }
    return { values: configValues(this.opts.cfg) };
  }

  async selectVoice(key) {
    if (this.switchingVoice || this.togglePromise || this.initialization || this.speaking) throw new Error('请等待当前语音操作完成后切换音色');
    this.runtime.assertVoiceSupported(key);
    voicePath(this.runtime.root, key);
    if ((this.opts.cfg.voiceId || BUILTIN) === key) return this.status();
    this.switchingVoice = true;
    const enabled = this.speechEnabled;
    try {
      await this.setSpeechEnabled(false);
      this.opts.persist?.({ voiceId: key });
      this.opts.cfg.voiceId = key;
      this.runtime.history = []; this.runtime.lastSpeech = null;
      this.writeSettings({ ...this.settings, selectedVoice: key });
      if (enabled) await this.setSpeechEnabled(true);
      return this.status();
    } finally { this.switchingVoice = false; }
  }

  assertIdleOperation() {
    if (!this.active || this.speaking || this.queue.length || this.initialization || this.togglePromise || this.switchingDevice || this.deviceChecking || this.updating || this.updates?.status().busy || this.reports?.status().busy) throw new Error('请等当前朗读、加载或更新结束后再操作');
  }

  async selectDevice(name) {
    this.assertIdleOperation();
    const patch=validateConfigPatch({deviceName:name});
    if(name===(this.opts.cfg.deviceName||''))return this.status();
    const previous=this.opts.cfg.deviceName||'',enabled=this.speechEnabled;
    const change=this.deviceChange={state:'checking',target:name,previous,startedAt:Date.now(),detail:'正在检查所选设备…'};
    let mutated=false;this.deviceChecking=true;
    try {
      if(name){const result=await this.runtime.devices();if(result.devices.filter(d=>d.name===name).length!==1)throw new Error('设备不存在或名称不唯一；不会自动切换到其他显卡');}
      this.deviceChecking=false;this.assertIdleOperation();this.switchingDevice=true;mutated=true;
      Object.assign(change,{state:'loading',detail:'正在释放原设备并加载所选设备…'});
      await this.setSpeechEnabled(false);
      Object.assign(this.opts.cfg,patch);this.opts.persist?.(patch);
      this.writeSettings({...this.settings,config:configValues(this.opts.cfg)});
      this.runtime.history=[];this.runtime.lastSpeech=null;
      if(enabled){await this.setSpeechEnabled(true);await this.initialization;}
      Object.assign(change,{state:'success',detail:'已选择并保存：'+(name||'按安装配置选择')+(enabled?'；语音已重新加载。':'；下次开启语音时使用。'),finishedAt:Date.now()});
    } catch(error) {
      let detail='设备未切换：'+error.message;
      if(mutated){
        try {
          await this.setSpeechEnabled(false);
          this.opts.cfg.deviceName=previous;this.opts.persist?.({deviceName:previous});
          this.writeSettings({...this.settings,config:configValues(this.opts.cfg)});
          if(enabled){await this.setSpeechEnabled(true);await this.initialization;}
          detail='设备切换失败，已恢复原设备配置：'+error.message;
        } catch(restoreError){detail='设备切换失败：'+error.message+'；恢复也失败：'+restoreError.message+'。请检查运行状态后重试。';}
      }
      Object.assign(change,{state:'error',detail,finishedAt:Date.now()});throw new Error(detail);
    } finally {this.switchingDevice=false;this.deviceChecking=false;}
    return this.status();
  }

  async applyUpdate() {
    this.assertIdleOperation();
    if(!this.opts.botDir)throw new Error('缺少桌宠部署目录，请使用完整包重新安装');
    this.updating=true;const enabled=this.speechEnabled;
    try {
      await this.setSpeechEnabled(false);
      await this.updates.run('apply',join(this.opts.botDir,'..','..','extensions'));
      return this.updates.status();
    } finally {
      this.updating=false;
      if(enabled&&this.active){await this.setSpeechEnabled(true);await this.initialization?.catch(err=>this.host?.log.warn('更新后启动失败：'+err.message));}
    }
  }

  async setSpeechEnabled(enabled) {
    if (this.togglePromise) {
      await this.togglePromise;
      if (this.speechEnabled === enabled) return this.status();
    }
    this.togglePromise = (async () => {
      this.writeSettings({ ...this.settings, speechEnabled: enabled, config: configValues(this.opts.cfg) });
      this.speechEnabled = enabled;
      if (!enabled) {
        this.bubbleSync.cancelAll();
        this.accepting = false;
        this.blocked = true;
        this.queue.length = 0;
        await this.sleepPromise;
        await this.runtime.stop();
        await this.draining;
        await this.initialization?.catch(() => {});
        this.runtime.stage('disabled', '语音已停用；模型与环境保留，worker 已停止。');
      } else if (this.runtime.hasLocalFiles()) {
        void this.initialize(false).catch(err => this.host?.log.warn(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 启用失败: ${err.message}`));
      } else this.runtime.stage('waiting_user', '已开启语音，但本机环境未完整；请手动安装／修复。');
    })().finally(() => { this.togglePromise = null; });
    await this.togglePromise;
    return this.status();
  }

  async initialize(allowInstall) {
    if (this.initialization) return this.initialization;
    const runtime = this.runtime;
    this.initialization = (async () => {
      if (allowInstall) await runtime.prepare();
      if (!this.active || this.runtime !== runtime) return;
      if (!this.speechEnabled) {
        runtime.stage('disabled', '环境与模型已安装；语音保持停用，点击「启用语音」开始使用。');
        return;
      }
      await this.sleepPromise;
      await runtime.ensure({ allowInstall: false });
      if (!this.active || this.runtime !== runtime) return;
      if (!this.speechEnabled) return;
      if (!this.accepting) this.tailer?.skipHistory();
      this.accepting = true;
      this.lastActivity = Date.now();
      this.blocked = false;
      if (!this.speaking) { this.draining = this.drain(); await this.draining; }
    })().catch(err => {
      if (this.active && this.runtime === runtime) {
        this.blocked = true;
        if (/GiB free RAM|keeping text only/.test(err.message)) runtime.stage('waiting_memory', `内存不足，暂用文字；可用内存达到 ${runtime.memoryPolicy().recoveryGiB} GiB 后自动恢复。也可在语音控制页重试。`);
      }
      throw err;
    }).finally(() => { this.initialization = null; });
    return this.initialization;
  }

  async stop() {
    this.bubbleSync.cancelAll();
    this.removeBubbleBridge?.();this.removeBubbleBridge=null;
    this.active = false;
    this.accepting = false;
    this.blocked = true;
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
    this.queue.length = 0;
    await this.updatePolling?.catch(()=>{});
    await this.updates?.running?.catch(()=>{});
    await this.reports?.running?.catch(()=>{});
    await this.sleepPromise;
    await this.runtime?.stop();
    await this.draining;
    await this.initialization?.catch(() => {});
    await this.togglePromise?.catch(() => {});
    this.runtime = null;
    this.host = null;
  }

  onToolCall(entry) {
    // Preserve completed text output even when audio is muted, loading or disabled.
    this.recentReplies = rememberReply(this.recentReplies, entry);
    const item = petSayFromEntry(entry);
    if (!item || item.seq <= (this.lastSeen[item.run] || 0)) return true;
    if (!this.speechEnabled || !this.accepting || this.opts.cfg.volume === 0) { ++this.skippedBeforeReady; return true; }
    const max = Math.max(1, Number(this.opts.cfg.maxQueue) || 12);
    if (this.blocked) return true;
    if (this.queue.length >= max) { const old=this.queue.shift();this.bubbleSync.finish(old.key,'expired'); ++this.dropped; }
    this.lastSeen[item.run] = item.seq;
    if (Object.keys(this.lastSeen).length > 16) delete this.lastSeen[Object.keys(this.lastSeen)[0]];
    this.queue.push({ ...item, receivedAt: Date.now() });
    this.bubbleSync.track(item);
    if (!this.speaking) this.draining = this.drain();
    return true;
  }

  async drain() {
    if (this.speaking || !this.runtime || this.blocked || !this.active || !this.speechEnabled) return;
    this.speaking = true;
    try {
      while (this.queue.length && this.runtime && this.active && this.speechEnabled && !this.blocked) {
        const item = this.queue.shift();
        if (this.opts.cfg.volume === 0 || Date.now() - item.receivedAt > this.opts.cfg.maxAgeSec * 1000) { this.bubbleSync.finish(item.key,'skipped');++this.dropped; continue; }
        try {
          await this.sleepPromise;
          if (!this.active || !this.speechEnabled || this.blocked || !this.runtime) break;
          if(this.removeBubbleBridge)await this.bubbleSync.waitUntilShown(item.key);
          if(!this.active||!this.speechEnabled||this.blocked||!this.runtime){this.bubbleSync.finish(item.key,'cancelled');break;}
          if(this.opts.cfg.volume===0){this.bubbleSync.finish(item.key,'skipped');continue;}
          this.host?.log.info(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎: ${item.text}`);
          await this.runtime.speak(item.text, { receivedAt: item.receivedAt });
          this.bubbleSync.finish(item.key);
        } catch (err) {
          this.bubbleSync.finish(item.key,'failed');
          if(err.code==='generation_limit' && err.recoverable===true) {
            this.host?.log.warn(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 单句未完成，继续后续消息: ${err.message}`);
            continue;
          }
          for(const waiting of this.queue)this.bubbleSync.finish(waiting.key,'cancelled');
          this.host?.log.warn(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 朗读失败: ${err.message}`);
          // Never repeat a partially spoken sentence automatically.
          this.blocked = true; this.accepting = false;
          if (/GiB free RAM|keeping text only/.test(err.message)) this.runtime?.stage('waiting_memory', `内存不足，暂用文字；达到 ${this.runtime.memoryPolicy().recoveryGiB} GiB 后可自动恢复。`);
        }
      }
    } finally {
      this.lastActivity = Date.now();
      this.speaking = false;
    }
  }

  saveCursor(cursor) {
    if (!this.cursorFile || !this.active) return;
    mkdirSync(dirname(this.cursorFile), { recursive: true });
    writeFileSync(this.cursorFile + '.tmp', JSON.stringify({ ...cursor, lastSeen: this.lastSeen, recentReplies: this.recentReplies }), 'utf8');
    renameSync(this.cursorFile + '.tmp', this.cursorFile);
  }
}
