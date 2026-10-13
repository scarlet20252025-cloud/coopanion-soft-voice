import { existsSync, readdirSync, readFileSync, statSync, writeFileSync, unlinkSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
export const BUILTIN = 'builtin';
export const TUTORIAL = 'https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/VOICE_PACKS.md';
export function listVoices(root) {
  const result = [{ key: BUILTIN, name: '当前已确认音色', description: 'soft-child-design-2 · 内置音色', available: true },
    { key: 'future-default', name: '新版默认音色 · 待更新', description: '预留位置，尚未发布', available: false }];
  const folder = join(root, 'voices');
  if (existsSync(folder)) for (const key of readdirSync(folder)) {
    if (!/^[a-z][a-z0-9-]{2,47}-[a-f0-9]{12}$/.test(key)) continue;
    try {
      const file = join(folder, key, 'voice.json');
      if (statSync(file).size > 16000) continue;
      const m = JSON.parse(readFileSync(file, 'utf8'));
      if (m.format !== 'local-voice-pack' || m.version !== 1) continue;
      result.push({ key, name: m.name, description: `已导入 · ${Number(m.duration).toFixed(1)} 秒参考音频`, available: true });
    } catch { /* Incomplete packages are not selectable. */ }
  }
  return result;
}
export function voicePath(root, key) {
  if (key === BUILTIN) return null;
  if (!listVoices(root).some(v => v.key === key && v.available)) throw new Error('此音色不可用或尚待更新');
  return join(root, 'voices', key);
}
export async function importVoice(runtime, base64) {
  if (typeof base64 !== 'string' || base64.length > 2800000 || !/^[A-Za-z0-9+/]*={0,2}$/.test(base64)) throw new Error('请选择不超过 2 MiB 的 ZIP 音色包');
  const buffer = Buffer.from(base64, 'base64');
  if (!buffer.length || buffer.length > 2*1024*1024) throw new Error('ZIP 大小无效');
  const folder = join(runtime.root, 'imports'); mkdirSync(folder, { recursive: true });
  const file = join(folder, randomUUID() + '.zip'); writeFileSync(file, buffer, { flag: 'wx' });
  try {
    return await new Promise((resolve, reject) => {
      const p = spawn(runtime.profile().python, ['-m', 'coopanion_soft_voice.voice_pack', 'import', '--zip', file, '--root', join(runtime.root, 'voices')],
        { windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
      let out = '', err = '';
      const timer = setTimeout(() => { p.kill(); reject(new Error('导入超时')); }, 15000);
      p.stdout.setEncoding('utf8'); p.stderr.setEncoding('utf8');
      p.stdout.on('data', s => { out = (out + s).slice(-32000); });
      p.stderr.on('data', s => { err = (err + s).slice(-4000); });
      p.once('error', e => { clearTimeout(timer); reject(e); });
      p.once('close', code => {
        clearTimeout(timer);
        if (code) return reject(new Error(err.split('\n').filter(Boolean).at(-1) || '导入失败'));
        try { resolve(JSON.parse(out)); } catch { reject(new Error('导入结果无效')); }
      });
    });
  } finally { unlinkSync(file); }
}
