import { appendFileSync, cpSync, createWriteStream, existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { StringDecoder } from 'node:string_decoder';
import { createHash } from 'node:crypto';
import { volumePercent } from './config.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(HERE, '..');
const INFERENCE_REQ = resolve(HERE, '../runtime/requirements-inference.txt');
const CONSTRAINTS = resolve(HERE, '../runtime/constraints-inference.txt');
const WORKER = resolve(HERE, '../runtime/worker.py');
const UV_URL = 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip';
const COSY_URL = 'https://github.com/FunAudioLLM/CosyVoice/archive/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc.zip';
const MATCHA_URL = 'https://github.com/shivammehta25/Matcha-TTS/archive/dd9105b34bf2be2230f4aa1e4769fb586a3c824e.zip';
const DEFAULT_REF_URL = 'https://huggingface.co/spaces/FunAudioLLM/Fun-CosyVoice3-0.5B/resolve/main/zero_shot_prompt.wav';
const MODEL_MARKER = '.download-complete';
const PREFLIGHT = resolve(HERE, '../runtime/preflight.py');
const MANIFEST = JSON.parse(readFileSync(resolve(HERE, '../runtime/model-manifest.json'), 'utf8'));

function run(cmd, args, opts = {}) {
  return new Promise((ok, fail) => {
    const p = spawn(cmd, args, { windowsHide: true, ...opts });
    let stderr = '';
    const outDecoder = new StringDecoder('utf8'), errDecoder = new StringDecoder('utf8');
    p.stderr?.on('data', d => { const s = errDecoder.write(d); stderr += s; opts.onStderr?.(s); });
    p.stdout?.on('data', d => opts.onStdout?.(outDecoder.write(d)));
    p.once('error', fail);
    p.once('close', code => {
      opts.onStdout?.(outDecoder.end()); stderr += errDecoder.end();
      if (code === 0) ok(); else { const err = new Error(`${cmd} 退出码 ${code}: ${stderr.slice(-12000)}`); err.exitCode = code; err.stderr = stderr; fail(err); }
    });
  });
}

async function download(url, file, onProgress, signal) {
  mkdirSync(dirname(file), { recursive: true });
  const res = await fetch(url, { redirect: 'follow', signal });
  if (!res.ok || !res.body) throw new Error(`下载失败 ${res.status}: ${url}`);
  const total = Number(res.headers.get('content-length')) || null;
  let done = 0, last = -1;
  const body = Readable.fromWeb(res.body);
  body.on('data', chunk => {
    done += chunk.length;
    if (total) {
      const pct = Math.floor(done / total * 100);
      if (pct >= last + 5) { last = pct; onProgress?.(pct, done, total); }
    } else {
      onProgress?.(null, done, null);
    }
  });
  const partial = file + '.partial';
  rmSync(partial, { force: true });
  const out = createWriteStream(partial);
  await pipeline(body, out);
  rmSync(file, { force: true });
  renameSync(partial, file);
}

function findFile(root, name, depth = 5) {
  if (!existsSync(root) || depth < 0) return null;
  for (const e of readdirSync(root, { withFileTypes: true })) {
    const p = join(root, e.name);
    if (e.isFile() && e.name.toLowerCase() === name.toLowerCase()) return p;
  }
  for (const e of readdirSync(root, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const hit = findFile(join(root, e.name), name, depth - 1);
    if (hit) return hit;
  }
  return null;
}

function dirSize(root, depth = 12) {
  if (!existsSync(root) || depth < 0) return 0;
  let total = 0;
  try {
    for (const e of readdirSync(root, { withFileTypes: true })) {
      const p = join(root, e.name);
      try {
        if (e.isFile()) total += statSync(p).size;
        else if (e.isDirectory()) total += dirSize(p, depth - 1);
      } catch {}
    }
  } catch {}
  return total;
}

async function unzip(zip, dest) {
  mkdirSync(dest, { recursive: true });
  const ps = process.env.SystemRoot ? join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe') : 'powershell.exe';
  await run(ps, ['-NoProfile', '-NonInteractive', '-Command', `Expand-Archive -LiteralPath '${zip.replace(/'/g, "''")}' -DestinationPath '${dest.replace(/'/g, "''")}' -Force`], { stdio: ['ignore', 'ignore', 'pipe'] });
}

function firstDirectory(root) {
  return readdirSync(root, { withFileTypes: true }).find(e => e.isDirectory())?.name ?? null;
}

export function validateModel(modelDir) {
  const configPath = join(dirname(dirname(modelDir)), 'kokoro-settings.json');
  const config = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf8')) : null;
  const files = config && modelDir.endsWith(config.modelFolder) ? config.files : MANIFEST.files;
  const missing = [];
  for (const [file, expected] of Object.entries(files)) {
    try {
      const actual = statSync(join(modelDir, file)).size;
      if (actual !== expected) missing.push({ file, expected, actual });
    } catch { missing.push({ file, expected, actual: null }); }
  }
  return { ok: missing.length === 0, missing };
}

export function runtimeEnvironment(root, { offline = false } = {}) {
  const env = { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8',
    UV_PYTHON_INSTALL_DIR: join(root, 'python'), UV_PYTHON_PREFERENCE: 'only-managed',
    UV_PYTHON_BIN_DIR: join(root, 'tools', 'python-bin'),
    UV_TOOL_DIR: join(root, 'tools', 'uv-tools'), UV_TOOL_BIN_DIR: join(root, 'tools', 'bin'),
    UV_CACHE_DIR: join(root, 'cache', 'uv'), HF_HOME: join(root, 'cache', 'huggingface'),
    HF_HUB_CACHE: join(root, 'cache', 'huggingface', 'hub'),
    HF_XET_CACHE: join(root, 'cache', 'huggingface', 'xet'),
    TORCH_HOME: join(root, 'cache', 'torch'), XDG_CACHE_HOME: join(root, 'cache'),
    MPLCONFIGDIR: join(root, 'cache', 'matplotlib'), NUMBA_CACHE_DIR: join(root, 'cache', 'numba'),
    MODELSCOPE_CACHE: join(root, 'cache', 'modelscope'),
    TMP: join(root, 'cache', 'tmp'), TEMP: join(root, 'cache', 'tmp'), TMPDIR: join(root, 'cache', 'tmp'),
  };
  env.HUGGINGFACE_HUB_CACHE = env.HF_HUB_CACHE;
  if (offline) {
    env.HF_HUB_OFFLINE = '1';
    env.TRANSFORMERS_OFFLINE = '1';
  }
  for (const key of ['UV_PYTHON_INSTALL_DIR', 'UV_PYTHON_BIN_DIR', 'UV_TOOL_DIR', 'UV_TOOL_BIN_DIR', 'UV_CACHE_DIR', 'HF_HOME', 'HF_HUB_CACHE',
    'HF_XET_CACHE', 'TORCH_HOME', 'MPLCONFIGDIR', 'NUMBA_CACHE_DIR', 'MODELSCOPE_CACHE', 'TMP']) {
    mkdirSync(env[key], { recursive: true });
  }
  return env;
}

export class CosyRuntime {
  constructor({ cfg, log }) {
    this.cfg = cfg;
    this.log = log;
    this.pluginRoot = PLUGIN_ROOT;
    this.root = join(PLUGIN_ROOT, '.cosyvoice-tts');
    this.state = { phase: 'idle', stage: 'idle', detail: '尚未初始化' };
    this.installPromise = null;
    this.preparePromise = null;
    this.readyPromise = null;
    this.worker = null;
    this.pending = new Map();
    this.seq = 0;
    this.generation = 0;
    this.controller = new AbortController();
    this.preflightResult = null;
    this.workerError = null;
    this.workerTrace = null;
    this.workerStderr = '';
    this.workerExitCode = null;
    this.lastError = null;
    this.sizeCache = { at: 0, bytes: 0, changedAt: null };
    this.stdoutCarry = '';
    this.initializing = false;
    this.lastSpeech = null;
  }

  python() { return join(this.root, 'venv', 'Scripts', 'python.exe'); }
  sourceDir() { return join(this.root, 'CosyVoice'); }
  modelDir() { const path = join(this.root, 'kokoro-settings.json'); const cfg = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null; return join(this.root, 'models', cfg?.modelFolder || 'Fun-CosyVoice3-0.5B-2512'); }
  defaultRef() { return join(this.root, 'assets', 'zero_shot_prompt.wav'); }
  workerLog() { return join(this.root, 'logs', 'worker.log'); }
  marker() { return join(this.root, 'venv', '.cosyvoice-deps-v4'); }

  hasLocalFiles() {
    const ref = this.cfg.referenceAudio?.trim() ? resolve(this.pluginRoot, this.cfg.referenceAudio.trim()) : this.defaultRef();
    return existsSync(this.python()) && existsSync(join(this.sourceDir(), 'cosyvoice', 'cli', 'cosyvoice.py')) &&
      existsSync(join(this.sourceDir(), 'third_party', 'Matcha-TTS', 'matcha', 'models', 'components', 'flow_matching.py')) &&
      existsSync(ref) && validateModel(this.modelDir()).ok;
  }

  stage(stage, detail) {
    this.state = { phase: stage, stage, detail };
    this.log?.info?.('CosyVoice TTS: ' + detail);
    this.appendWorkerLog(stage, detail);
  }

  status() {
    const now = Date.now();
    if (now - this.sizeCache.at > 2000) {
      const bytes = dirSize(this.modelDir());
      this.sizeCache = { at: now, bytes, changedAt: bytes !== this.sizeCache.bytes ? new Date().toISOString() : this.sizeCache.changedAt };
    }
    const model = validateModel(this.modelDir());
    return { ...this.state, root: this.root, pluginRoot: this.pluginRoot,
      uvReady: !!findFile(join(this.root, 'tools', 'uv'), 'uv.exe'),
      pythonReady: existsSync(this.python()),
      sourceReady: existsSync(join(this.sourceDir(), 'cosyvoice', 'cli', 'cosyvoice.py')),
      depsReady: this.preflightResult?.ok === true, preflight: this.preflightResult,
      referenceReady: existsSync(this.cfg.referenceAudio?.trim() ? resolve(this.pluginRoot, this.cfg.referenceAudio.trim()) : this.defaultRef()),
      modelReady: model.ok, modelMissing: model.missing, modelBytes: this.sizeCache.bytes,
      modelChangedAt: this.sizeCache.changedAt, downloadTotal: this.downloadTotal ?? null,
      downloadedBytes: this.downloadedBytes ?? null, downloadPercent: this.downloadPercent ?? null,
      cuda: this.preflightResult?.cuda ?? null, gpu: this.preflightResult?.device ?? null,
      torch: this.preflightResult?.torch ?? null,
      device: this.preflightResult ? (this.preflightResult.cuda ? this.preflightResult.device : 'CPU') : null,
      workerPid: this.worker?.pid ?? null, workerLog: this.workerLog(),
      initializing: this.initializing, lastSpeech: this.lastSpeech,
      workerError: this.workerError, workerTrace: this.workerTrace,
      workerStderr: this.workerStderr, workerExitCode: this.workerExitCode, lastError: this.lastError };
  }

  appendWorkerLog(kind, text) {
    try {
      mkdirSync(dirname(this.workerLog()), { recursive: true });
      appendFileSync(this.workerLog(), '[' + new Date().toISOString() + '] ' + kind + ' ' + String(text) + '\n', 'utf8');
    } catch (err) { this.log?.warn?.('worker.log 写入失败: ' + err.message); }
  }

  captureError(error, stage = this.state.stage) {
    const detail = error.report || error;
    this.lastError = { type: 'error', stage: detail.stage || stage,
      exceptionType: detail.exceptionType || error.name || 'Error',
      error: detail.error || error.message || String(error),
      trace: detail.trace || detail.traceback || error.stack || '',
      stderr: detail.stderr || error.stderr || this.workerStderr,
      exitCode: detail.exitCode ?? error.exitCode ?? this.workerExitCode };
    this.workerError = this.lastError.exceptionType + ': ' + this.lastError.error;
    this.workerTrace = this.lastError.trace;
    this.state = { phase: 'error', stage: this.lastError.stage, detail: this.workerError };
    this.appendWorkerLog('ERROR', JSON.stringify(this.lastError));
    return error;
  }

  async ensure({ allowInstall = false } = {}) {
    if (this.readyPromise) return this.readyPromise;
    if (this.controller.signal.aborted) this.controller = new AbortController();
    const generation = this.generation;
    this.initializing = true;
    this.readyPromise = (async () => {
      await this.installEnvironment({ allowInstall });
      if (generation !== this.generation) throw new Error('初始化已取消');
      await this.startWorker({ allowDownload: allowInstall });
    })().catch(err => {
      if (generation === this.generation) { this.captureError(err); this.readyPromise = null; }
      throw err;
    }).finally(() => { if (generation === this.generation) this.initializing = false; });
    return this.readyPromise;
  }

  async prepare() {
    if (this.preparePromise) return this.preparePromise;
    if (this.controller.signal.aborted) this.controller = new AbortController();
    const generation = this.generation;
    this.initializing = true;
    this.preparePromise = (async () => {
      await this.installEnvironment({ allowInstall: true });
      if (generation !== this.generation) throw new Error('安装已取消');
      await this.prepareModel();
    })().catch(err => {
      if (generation === this.generation) this.captureError(err);
      throw err;
    }).finally(() => {
      this.preparePromise = null;
      if (generation === this.generation) this.initializing = false;
    });
    return this.preparePromise;
  }

  async prepareModel() {
    this.stage('validate_model', '离线检查模型关键文件');
    if (validateModel(this.modelDir()).ok) return;
    let carry = '', report = null, prepared = false;
    try {
      await run(this.python(), this.workerArguments({ allowDownload: true, prepareOnly: true }), {
        env: runtimeEnvironment(this.root), signal: this.controller.signal, stdio: ['ignore', 'pipe', 'pipe'],
        onStderr: s => { this.workerStderr = (this.workerStderr + s).slice(-32000); this.appendWorkerLog('STDERR', s); },
        onStdout: s => {
          this.onStdout(s);
          carry += s; const lines = carry.split(/\r?\n/); carry = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('@@COSY@@')) continue;
            try { const msg = JSON.parse(line.slice(8)); if (msg.type === 'error') report = msg; if (msg.type === 'prepared') prepared = true; }
            catch (err) { report = { stage: 'ipc', exceptionType: err.name, error: err.message }; }
          }
        }
      });
    } catch (err) { if (report) err.report = report; throw err; }
    if (!prepared || !validateModel(this.modelDir()).ok) throw new Error('安装进程没有返回完整模型确认');
  }

  async preflight() {
    this.stage('preflight', '验证当前桌宠语音运行环境');
    let stdout = '', stderr = '', exitError = null;
    try {
      await run(this.python(), [PREFLIGHT, '--source', this.sourceDir(), '--root', this.root,
        '--model-dir', this.modelDir(), '--ipc'], {
        env: runtimeEnvironment(this.root, { offline: true }), signal: this.controller.signal,
        stdio: ['ignore', 'pipe', 'pipe'],
        onStdout: s => { stdout += s; }, onStderr: s => { stderr += s; this.appendWorkerLog('PREFLIGHT_STDERR', s); }
      });
    } catch (err) { exitError = err; }
    const line = stdout.split(/\r?\n/).findLast(s => s.startsWith('@@COSY@@'));
    let report;
    try { report = line ? JSON.parse(line.slice(8)) : null; } catch { report = null; }
    if (!report) {
      const err = exitError || new Error('preflight 未返回有效 JSON');
      this.preflightResult = { ok: false, stage: 'preflight', exceptionType: err.name, error: err.message, stderr };
      err.report = this.preflightResult;
      throw err;
    }
    this.preflightResult = report;
    this.appendWorkerLog('PREFLIGHT', JSON.stringify(report));
    if (!report.ok || exitError) {
      const err = new Error(report.error || exitError?.message || 'preflight 失败');
      err.report = { ...report, stage: 'preflight', stderr, exitCode: exitError?.exitCode ?? 1 };
      throw err;
    }
    return report;
  }

  async installEnvironment({ allowInstall = false } = {}) {
    if (this.installPromise) return this.installPromise;
    const generation = this.generation;
    this.installPromise = this._install({ allowInstall }).catch(err => {
      if (generation === this.generation) this.captureError(err);
      throw err;
    }).finally(() => { this.installPromise = null; });
    return this.installPromise;
  }

  async _install({ allowInstall = false } = {}) {
    this.stage('check_environment', '检查插件运行环境');
    const env = runtimeEnvironment(this.root), signal = this.controller.signal;
    const command = (cmd, args) => run(cmd, args, { env, signal,
      stdio: ['ignore', 'pipe', 'pipe'],
      onStdout: s => this.appendWorkerLog('INSTALL_STDOUT', s),
      onStderr: s => { this.appendWorkerLog('INSTALL_STDERR', s); this.log?.info?.(s.trim()); }
    });
    const sourceOK = existsSync(join(this.sourceDir(), 'cosyvoice', 'cli', 'cosyvoice.py'));
    const matcha = join(this.sourceDir(), 'third_party', 'Matcha-TTS');
    const matchaOK = existsSync(join(matcha, 'matcha', 'models', 'components', 'flow_matching.py'));
    let healthy = false, preflightError = null;
    if (existsSync(this.python()) && sourceOK && matchaOK) {
      try { await this.preflight(); healthy = true; }
      catch (err) {
        if (signal.aborted) throw err;
        preflightError = err;
        this.appendWorkerLog('REPAIR_REQUIRED', err.message);
      }
    }
    if (!healthy) {
      if (!allowInstall) throw preflightError || new Error('本机环境不完整；请在运行状态点击「安装／修复环境与模型」。');
      let uv = findFile(join(this.root, 'tools', 'uv'), 'uv.exe');
      if (!uv) {
        this.stage('bootstrap_uv', '下载插件专用 uv');
        const zip = join(this.root, 'downloads', 'uv.zip');
        await download(UV_URL, zip, pct => this.stage('bootstrap_uv', '下载 uv ' + (pct == null ? '' : pct + '%')), signal);
        await unzip(zip, join(this.root, 'tools', 'uv'));
        uv = findFile(join(this.root, 'tools', 'uv'), 'uv.exe');
        if (!uv) throw new Error('下载后找不到 uv.exe');
      }
      if (!existsSync(this.python())) {
        this.stage('bootstrap_python', '准备独立 Python 3.10');
        await command(uv, ['python', 'install', '3.10', '--no-bin', '--no-registry']);
        this.stage('create_venv', '建立插件专用 venv');
        await command(uv, ['venv', '--python', '3.10', join(this.root, 'venv')]);
      }
      for (const [ok, stage, url, target] of [
        [sourceOK, 'bootstrap_source', COSY_URL, this.sourceDir()],
        [matchaOK, 'bootstrap_matcha', MATCHA_URL, matcha]
      ]) {
        if (ok) continue;
        this.stage(stage, '准备 ' + (stage === 'bootstrap_source' ? 'CosyVoice 源码' : 'Matcha-TTS'));
        const staging = join(this.root, 'downloads', stage + '-' + Date.now());
        const zip = staging + '.zip';
        await download(url, zip, null, signal);
        await unzip(zip, staging);
        const first = firstDirectory(staging);
        if (!first) throw new Error('原始码压缩包为空');
        // Overlay an incomplete source tree; never delete existing runtime/model data.
        cpSync(join(staging, first), target, { recursive: true });
      }
      await this.installDependencies(uv, command);
      await this.preflight(); // Sole health authority, including old marker upgrades.
    }
    writeFileSync(this.marker(), JSON.stringify({ version: 4, checkedAt: new Date().toISOString(),
      requirements: createHash('sha256').update(readFileSync(INFERENCE_REQ)).digest('hex'),
      torch: this.preflightResult.torch }), 'utf8');
    if (!this.cfg.referenceAudio?.trim() && !existsSync(this.defaultRef())) {
      if (!allowInstall) throw new Error('参考音频不存在；请在运行状态点击「安装／修复环境与模型」。');
      this.stage('download_reference', '下载官方 zero-shot 参考音频');
      await download(DEFAULT_REF_URL, this.defaultRef(), null, signal);
    }
    this.stage('installed', '依赖 preflight 已通过');
  }

  async installDependencies(uv, command) {
    this.stage('install_torch', '安装 / 修复 PyTorch CUDA 12.1');
    await command(uv, ['pip', 'install', '--python', this.python(), 'torch==2.3.1', 'torchaudio==2.3.1',
      '--index-url', 'https://download.pytorch.org/whl/cu121']);
    this.stage('install_dependencies', '准备 Whisper 构建工具');
    await command(uv, ['pip', 'install', '--python', this.python(), 'setuptools==75.8.0', 'wheel==0.45.1', 'packaging>=24,<25']);
    this.stage('install_dependencies', '非隔离安装 OpenAI Whisper');
    await command(uv, ['pip', 'install', '--python', this.python(), '--no-build-isolation',
      '--constraint', CONSTRAINTS, 'openai-whisper==20231117']);
    this.stage('install_dependencies', '安装完整 CosyVoice / Matcha 推理依赖');
    await command(uv, ['pip', 'install', '--python', this.python(), '-r', INFERENCE_REQ]);
    await command(uv, ['pip', 'check', '--python', this.python()]);
  }

  workerArguments({ allowDownload = false, prepareOnly = false } = {}) {
    const ref = this.cfg.referenceAudio?.trim() ? resolve(this.pluginRoot, this.cfg.referenceAudio.trim()) : this.defaultRef();
    return [WORKER, '--source', this.sourceDir(), '--root', this.root,
      '--model-dir', this.modelDir(), '--model-repo', this.cfg.modelRepo || MANIFEST.repo,
      '--default-ref', ref, '--reference-text', this.cfg.referenceAudio?.trim() ? (this.cfg.referenceText || '') : '希望你以后能够做的比我还好呦。',
      ...(!allowDownload ? ['--no-download'] : []), ...(prepareOnly ? ['--prepare-only'] : []), ...(this.cfg.fp16 ? ['--fp16'] : [])];
  }

  async startWorker({ allowDownload = false } = {}) {
    if (this.worker) return;
    this.lastError = null;
    this.workerError = null;
    this.workerTrace = null;
    this.workerStderr = '';
    this.workerExitCode = null;
    this.stdoutCarry = '';
    const generation = this.generation;
    const ready = new Promise((resolve, reject) => this.pending.set('__ready__', { resolve, reject }));
    const args = this.workerArguments({ allowDownload });
    this.appendWorkerLog('START', this.python() + ' ' + JSON.stringify(args));
    const p = spawn(this.python(), args, { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: runtimeEnvironment(this.root, { offline: !allowDownload }) });
    this.worker = p;
    const stdout = new StringDecoder('utf8'), stderr = new StringDecoder('utf8');
    p.stdout.on('data', d => { if (generation === this.generation) this.onStdout(stdout.write(d)); });
    p.stderr.on('data', d => {
      if (generation !== this.generation) return;
      const text = stderr.write(d);
      this.workerStderr = (this.workerStderr + text).slice(-32000);
      this.appendWorkerLog('STDERR', text);
    });
    p.once('error', err => {
      if (generation !== this.generation) return;
      this.captureError(err, 'spawn_worker');
      this.rejectPending(err);
    });
    p.once('close', code => {
      if (generation !== this.generation) return;
      this.onStdout(stdout.end());
      const stderrTail = stderr.end();
      this.workerStderr += stderrTail;
      if (stderrTail) this.appendWorkerLog('STDERR', stderrTail);
      if (this.worker === p) this.worker = null;
      this.workerExitCode = code;
      this.appendWorkerLog('EXIT', String(code));
      if (this.lastError) {
        this.lastError.exitCode = code;
        this.lastError.stderr = this.workerStderr;
        this.state.detail = this.workerError + '\n[worker exit code: ' + code + ']';
      } else this.captureError(new Error(this.workerStderr.trim() || 'worker 已退出'), this.state.stage);
      this.rejectPending(new Error(this.state.detail));
      this.readyPromise = null;
    });
    const deadline = setTimeout(() => {
      const err = new Error('worker 初始化超过 30 分钟，请查看 worker.log');
      if (generation === this.generation) {
        this.captureError(err, this.state.stage); this.rejectPending(err); p.kill();
      }
    }, 30 * 60 * 1000);
    deadline.unref();
    try { await ready; }
    catch (err) {
      if (p.exitCode == null && !p.killed) {
        p.kill();
        await new Promise(done => { p.once('close', done); setTimeout(done, 2500).unref(); });
      }
      throw err;
    } finally { clearTimeout(deadline); }
    this.lastError = null;
    this.workerError = null;
    this.workerTrace = null;
  }

  rejectPending(err) {
    for (const v of this.pending.values()) v.reject(err);
    this.pending.clear();
  }

  onStdout(chunk) {
    this.appendWorkerLog('STDOUT', chunk);
    this.stdoutCarry += chunk;
    const lines = this.stdoutCarry.split(/\r?\n/);
    this.stdoutCarry = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('@@COSY@@')) continue;
      let msg;
      try { msg = JSON.parse(line.slice(8)); }
      catch (err) { this.captureError(err, 'ipc'); this.rejectPending(err); continue; }
      if (msg.type === 'status') {
        this.stage(msg.stage || msg.phase || 'loading', msg.detail || '');
        if (msg.stage === 'playing' && msg.id) {
          const pending = this.pending.get(msg.id);
          this.lastSpeech = { id: msg.id, text: pending?.text || '', synthesisMs: msg.synthesisMs,
            queueWaitMs: pending?.queueWaitMs ?? 0,
            startDelayMs: pending?.receivedAt ? Date.now() - pending.receivedAt : null };
        }
        if (msg.total != null) this.downloadTotal = msg.total;
        if (msg.bytes != null) this.downloadedBytes = msg.bytes;
        if (msg.percent != null) this.downloadPercent = msg.percent;
      } else if (msg.type === 'ready') {
        this.preflightResult = { ...this.preflightResult, ...msg.preflight };
        this.stage('ready', msg.device || 'CosyVoice3 已就绪');
        const wait = this.pending.get('__ready__');
        this.pending.delete('__ready__'); wait?.resolve(msg);
      } else if (msg.type === 'prepared') {
        this.preflightResult = { ...this.preflightResult, ...msg.preflight };
        this.stage('installed', '环境与模型已安装；尚未启用语音');
      } else if (msg.type === 'error') {
        const err = new Error(msg.error || 'TTS 失败');
        err.report = msg;
        this.captureError(err, msg.stage);
        const key = msg.id || '__ready__', wait = this.pending.get(key);
        this.pending.delete(key); wait?.reject(err);
      } else if (msg.type === 'done') {
        if (this.lastSpeech?.id === msg.id) { this.lastSpeech.seconds = msg.seconds; if (msg.totalSynthesisMs != null) this.lastSpeech.totalSynthesisMs = msg.totalSynthesisMs; }
        const wait = this.pending.get(msg.id);
        this.pending.delete(msg.id); wait?.resolve(msg);
        this.stage('ready', this.preflightResult?.backend === 'kokoro' ? 'Kokoro 萌趣声线已就绪' : '已就绪');
      }
    }
  }

  async speak(text, { receivedAt = Date.now() } = {}) {
    await this.ensure();
    if (!this.worker?.stdin?.writable) throw new Error('CosyVoice worker 不可写');
    const id = 's' + (++this.seq);
    const custom = !!this.cfg.referenceAudio?.trim();
    const payload = { id, text, referenceAudio: custom ? resolve(this.pluginRoot, this.cfg.referenceAudio.trim()) : this.defaultRef(),
      referenceText: custom ? (this.cfg.referenceText || '') : '希望你以后能够做的比我还好呦。',
      speed: Number(this.cfg.speed) || 1, volume: volumePercent(this.cfg.volume) };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, text, receivedAt, queueWaitMs: Date.now() - receivedAt });
      this.worker.stdin.write(JSON.stringify(payload) + '\n', err => {
        if (!err) return;
        this.pending.delete(id); this.captureError(err, 'ipc'); reject(err);
      });
    });
  }

  async openFolder() {
    mkdirSync(this.root, { recursive: true });
    const p = spawn('explorer.exe', [this.root], { detached: true, windowsHide: true, stdio: 'ignore' });
    p.unref();
    return this.root;
  }

  async clearData() {
    await this.stop();
    const expected = join(this.pluginRoot, '.cosyvoice-tts');
    if (resolve(this.root) !== resolve(expected)) throw new Error('拒绝删除非插件数据目录');
    rmSync(this.root, { recursive: true, force: true });
    this.preflightResult = null;
    this.lastError = null;
    this.workerError = null;
    this.workerTrace = null;
    this.workerStderr = '';
    this.workerExitCode = null;
    this.sizeCache = { at: 0, bytes: 0, changedAt: null };
    this.state = { phase: 'idle', stage: 'idle', detail: '运行环境与模型已删除' };
  }

  async stop() {
    ++this.generation;
    this.controller.abort();
    this.readyPromise = null;
    this.initializing = false;
    this.rejectPending(new Error('CosyVoice TTS 已停止'));
    this.state = { phase: 'stopped', stage: 'stopped', detail: '已停止' };
    const p = this.worker;
    this.worker = null;
    if (p) {
      try { p.stdin.write(JSON.stringify({ type: 'quit' }) + '\n'); } catch {}
      await new Promise(resolveStop => {
        const t = setTimeout(() => { p.kill(); resolveStop(); }, 2500);
        p.once('close', () => { clearTimeout(t); resolveStop(); });
      });
    }
    await this.installPromise?.catch(() => {});
    await this.preparePromise?.catch(() => {});
  }
}
