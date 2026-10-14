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

test('stop requested during an existing toggle is applied after that toggle', async () => {
  const w=world();w.speaking=false;w.writeSettings=s=>{w.settings=s;};
  let release,stops=0,phase='ready';
  w.togglePromise=new Promise(resolve=>{release=resolve;});
  w.runtime={status:()=>({phase}),stop:async()=>{stops++;},stage:p=>{phase=p;}};
  const stop=w.setSpeechEnabled(false);release();await stop;
  assert.equal(stops,1);assert.equal(w.speechEnabled,false);assert.equal(w.accepting,false);assert.equal(phase,'disabled');
});

test('cancel during model initialization does not restore enabled speech later', async () => {
  const w=world();w.speaking=false;w.accepting=false;w.speechEnabled=false;w.writeSettings=s=>{w.settings=s;};
  let rejectLoad,phase='load_model';
  const loading=new Promise((resolve,reject)=>{rejectLoad=reject;});
  w.runtime={hasLocalFiles:()=>true,ensure:()=>loading,status:()=>({phase}),stop:async()=>{rejectLoad(new Error('cancelled'));},stage:p=>{phase=p;}};
  await w.setSpeechEnabled(true);await w.setSpeechEnabled(false);
  assert.equal(w.speechEnabled,false);assert.equal(w.accepting,false);assert.equal(phase,'disabled');assert.equal(w.initialization,null);
});
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
  const r = Object.create(SoftVoiceRuntime.prototype); r.pending = new Map(); r.cfg={};
  let resolved = false; r.pending.set('s1', { receivedAt: Date.now(), resolve: () => { resolved = true; } });
  r.message({ type: 'status', stage: 'playing', id: 's1', synthesisMs: 900 });
  r.message({ type: 'done', id: 's1', underrunMs: 0, firstDeviceCallbackMs: 1100, processMemory:{privateMiB:2300,residentMiB:2500,peakResidentMiB:2600} });
  assert.equal(r.state.phase, 'ready'); assert.equal(r.lastSpeech.underrunMs, 0); assert.equal(resolved, true);
  assert.equal(r.status().processMemory.privateMiB,2300);
});

test('runtime memory guard follows the actual model layout and keeps fallback protection', async () => {
  const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');
  const {tmpdir}=await import('node:os');const {join}=await import('node:path');
  const dir=mkdtempSync(join(tmpdir(),'voice-policy-'));
  const r=Object.create(SoftVoiceRuntime.prototype);r.profile=()=>({runtime:dir});
  try {
    assert.equal(r.memoryPolicy().minimumGiB,4);
    const file=join(dir,'native-runtime.json');
    writeFileSync(file,JSON.stringify({compactGraphs:true,kvContext:1024,speechOnly:{format:1}}));
    assert.deepEqual(r.memoryPolicy(),{minimumGiB:3.5,recoveryGiB:4,layout:'compact'});
    writeFileSync(file,JSON.stringify({compactGraphs:false,kvContext:1024,speechOnly:{format:1}}));
    assert.equal(r.memoryPolicy().recoveryGiB,4.5);
  } finally {rmSync(dir,{recursive:true});}
});
test('panels have separate mounts and read-only status rejects mutations', async () => {
  const w=world();
  assert.deepEqual(w.console().panels.map(p=>p.id),['controls','status','config','voices']);
  await assert.rejects(w.console().invoke('status','disable'),/未知/);
  await assert.rejects(w.console().invoke('config','test'),/未知/);
  const ui=(await import('../dist/console-0.3.4.js')).default;
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

test('idle unloading defaults off, skips busy work, and wakes without losing queued speech', async () => {
  const w = world(); w.speaking = false; w.lastActivity = 0; w.opts.cfg.keepWorker=false;
  let stopped = 0; let phase = 'ready'; const spoken = [];
  w.runtime = { status: () => ({phase}), stop: async () => { stopped++; },
    stage: p => { phase=p; }, speak: async t => { phase='ready'; spoken.push(t); } };
  await w.maybeUnload(10000); assert.equal(stopped,0);
  w.opts.cfg.lowPowerMode = true; w.opts.cfg.idleUnloadSec = 1;
  w.speaking=true; await w.maybeUnload(10000); assert.equal(stopped,0);
  w.speaking=false; await w.maybeUnload(10000); assert.equal(stopped,1);
  assert.equal(phase,'sleeping'); assert.equal(w.accepting,true);
  assert.match(w.envPromptVars()['softVoice.state'],/待机/);
  w.onToolCall(entry(1)); await w.draining;
  assert.deepEqual(spoken,['你好呀']); assert.equal(w.queue.length,0);
  assert.equal(w.speechEnabled,true);
});

test('shutdown during idle unloading cannot restore sleeping state', async () => {
  const w=world(); w.speaking=false; w.lastActivity=0; w.opts.cfg.lowPowerMode=true; w.opts.cfg.idleUnloadSec=1; w.opts.cfg.keepWorker=false;
  let finish; let phase='ready';
  w.runtime={status:()=>({phase}),stop:()=>new Promise(r=>{finish=r;}),stage:p=>{phase=p;}};
  const sleeping=w.maybeUnload(10000); w.active=false; w.speechEnabled=false;
  finish(); await sleeping;
  assert.equal(phase,'ready'); assert.equal(w.sleepPromise,null);
});

test('low-memory protection sleeps only when idle and uses retained worker mode', async () => {
  const w=world(); w.speaking=false; w.opts.cfg.lowPowerMode=true; w.opts.cfg.lowMemoryMiB=1536; w.opts.cfg.keepWorker=true;
  let sleeps=0; let phase='ready';
  w.runtime={status:()=>({phase}),sleep:async()=>{sleeps++;},stage:p=>{phase=p;}};
  await w.maybeUnload(Date.now(),2000); assert.equal(sleeps,0);
  w.queue=[{}]; await w.maybeUnload(Date.now(),1000); assert.equal(sleeps,0);
  w.queue=[]; await w.maybeUnload(Date.now(),1000); assert.equal(sleeps,1);
  assert.equal(phase,'sleeping'); assert.equal(w.speechEnabled,true);
});


test('low power off suppresses BOTH idle and memory sleep without erasing thresholds', async () => {
  const w=world();w.speaking=false;w.lastActivity=0;
  let slept=0;w.runtime={status:()=>({phase:'ready'}),sleep:async()=>{slept++;},stage(){}};
  w.opts.cfg.lowPowerMode=false;w.opts.cfg.idleUnloadSec=1;w.opts.cfg.lowMemoryMiB=1536;
  await w.maybeUnload(999999,100);assert.equal(slept,0);
  w.opts.cfg.lowPowerMode=true;await w.maybeUnload(999999,100);assert.equal(slept,1);
});

test('disabling low power during sleep transition waits, then wakes', async () => {
  const w=world();w.speaking=false;w.opts.cfg.lowPowerMode=true;
  w.writeSettings=s=>{w.settings=s;};
  w.runtime={status:()=>({phase:'suspending'})};
  let finish,wakes=0;w.sleepPromise=new Promise(r=>{finish=r;});
  w.initialize=async()=>{wakes++;};
  w.saveConfig({lowPowerMode:false});await Promise.resolve();assert.equal(wakes,0);
  finish();await new Promise(r=>setImmediate(r));assert.equal(wakes,1);
  assert.equal(w.settings.config.lowPowerMode,false);
  assert.equal(w.settings.config.idleUnloadSec,300);
});
