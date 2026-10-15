import { DEFAULTS, ID } from './config.js';
import { SoftVoiceWorld } from './world.js';
import { restartRequest } from './restart.js';

const cloneDefaults = () => ({ ...DEFAULTS });

const definition = {
  id: ID,
  label: '轻核语音 · Qwen3-TTS 超轻量高速语音引擎',
  defaults: cloneDefaults,
  preflight: () => {
    if (process.platform !== 'win32') throw new Error('轻核语音 · Qwen3-TTS 超轻量高速语音引擎 0.1.0 需要 Windows。');
    if (process.arch !== 'x64') throw new Error(`轻核语音 · Qwen3-TTS 超轻量高速语音引擎 0.1.0 需要 Windows x64，当前是 ${process.arch}。`);
  },
  create: (ctx) => new SoftVoiceWorld({
    cfg: ctx.cfg,
    dataDir: ctx.dataDir,
    botDir: ctx.botDir,
    persist: ctx.persist,
    requestDesktopRestart:restartRequest(ctx.dataDir),
  })
};

export default definition;
