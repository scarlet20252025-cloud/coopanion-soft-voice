import test from 'node:test';
import assert from 'node:assert/strict';
import { SoftVoiceWorld } from '../src/world.js';
import { validateConfigPatch, DEFAULTS } from '../src/config.js';
import { petSayFromEntry } from '../src/parser.js';
import { SoftVoiceRuntime } from '../src/runtime.js';

function world() {
  const w = new SoftVoiceWorld({ cfg: {}, dataDir: '.' });
  w.active = true; w.accepting = true; w.speechEnabled = true;
  w.speaking = true; return w;
}
const entry = seq => ({ tool: 'pet_say', mod: 'desktop-pet', run: 'r-test', seq, args: { script: '【开心】你好呀' } });

test('official environment prompt declares template and reports real capability', async () => {
  const { readFileSync } = await import('node:fs');
  const w = world();
  const doc = w.console().promptDocs[0];
  assert.equal(doc.role, 'envPrompt');
  assert.match(readFileSync(doc.path, 'utf8'), /\{\{softVoice.state\}\}/);
  const state = () => w.envPromptVars()['softVoice.state'];
  assert.match(state(), /已就绪/);
  w.opts.cfg.volume = 0; assert.match(state(), /静音/);
  w.opts.cfg.volume = 65; w.blocked = true; assert.match(state(), /故障/);
  w.runtime = { status: () => ({ phase: 'waiting_memory' }) };
  assert.match(state(), /内存不足/);
  w.speechEnabled = false; assert.match(state(), /停用/);
  w.speechEnabled = true; w.blocked = false; w.accepting = false;
  w.runtime = { status: () => ({ phase: 'load_model' }) };
  assert.match(state(), /正在准备/);
});
test('standalone identity and validated effective controls', () => {
  assert.equal(world().id, 'soft-voice');
  assert.equal(world().console().label, '本地语音助手');
  assert.throws(() => validateConfigPatch({ speed: 1.2 }));
  assert.throws(() => validateConfigPatch({ volume: 101 }));
  assert.throws(() => validateConfigPatch({ autoRecover: 'true' }));
  assert.deepEqual(validateConfigPatch({ volume: 0 }), { volume: 0 });
});
test('parser strips stage directions and ignores failed calls', () => {
  assert.equal(petSayFromEntry(entry(1)).text, '你好呀');
  assert.equal(petSayFromEntry({ ...entry(1), failed: true }), null);
});
test('bounded queue drops oldest without replay; muted input is skipped', () => {
  const w = world(); w.opts.cfg.maxQueue = 2;
  [1, 2, 3].forEach(n => w.onToolCall(entry(n)));
  assert.deepEqual(w.queue.map(x => x.seq), [2, 3]); assert.equal(w.dropped, 1);
  w.onToolCall(entry(3)); assert.equal(w.queue.length, 2);
  w.opts.cfg.volume = 0; w.onToolCall(entry(4)); assert.equal(w.queue.length, 2);
});
test('expired queued speech is not synthesized', async () => {
  const w = world(); w.speaking = false;
  w.queue = [{ text: 'old', receivedAt: 0 }, { text: 'new', receivedAt: Date.now() }];
  const spoken = []; w.runtime = { speak: async t => spoken.push(t) };
  await w.drain(); assert.deepEqual(spoken, ['new']); assert.equal(w.dropped, 1);
});
test('failed partly spoken sentence is not automatically replayed', async () => {
  const w = world(); w.speaking = false;
  w.queue = [{ text: 'fail', receivedAt: Date.now() }];
  w.runtime = { speak: async () => { throw new Error('device lost'); } };
  await w.drain(); assert.equal(w.queue.length, 0); assert.equal(w.blocked, true); assert.equal(w.accepting, false);
});
test('wire metrics resolve speech and restore ready state', () => {
  const r = Object.create(SoftVoiceRuntime.prototype); r.pending = new Map();
  let resolved = false; r.pending.set('s1', { receivedAt: Date.now(), resolve: () => { resolved = true; } });
  r.message({ type: 'status', stage: 'playing', id: 's1', synthesisMs: 900 });
  r.message({ type: 'done', id: 's1', underrunMs: 0, firstDeviceCallbackMs: 1100 });
  assert.equal(r.state.phase, 'ready'); assert.equal(r.lastSpeech.underrunMs, 0); assert.equal(resolved, true);
});
test('panels have separate mounts and read-only status rejects mutations', async () => {
  const w=world();
  assert.deepEqual(w.console().panels.map(p=>p.id),['controls','status','config','voices']);
  await assert.rejects(w.console().invoke('status','disable'),/未知/);
  await assert.rejects(w.console().invoke('config','test'),/未知/);
  const ui=(await import('../dist/console-v2.js')).default;
  assert.equal(new Set(Object.values(ui.panels).map(p=>p.mount)).size,4);
});
test('future voice is unavailable and cannot become a filesystem path', async () => {
  const {voicePath,listVoices}=await import('../src/voices.js');
  assert.equal(listVoices('.').find(v=>v.key==='future-default').available,false);
  assert.throws(()=>voicePath('.','../escape'));
  assert.throws(()=>voicePath('.','future-default'));
  assert.equal(voicePath('.','builtin'),null);
});

test('fixed-voice rejection keeps current speech enabled', async () => {
  const w = world(); w.speaking = false;
  w.runtime = { assertVoiceSupported: () => { throw new Error('固定音色'); } };
  await assert.rejects(w.selectVoice('another-voice'), /固定音色/);
  assert.equal(w.speechEnabled, true);
  assert.equal(w.accepting, true);
});
