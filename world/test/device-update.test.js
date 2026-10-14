import test from 'node:test';
import assert from 'node:assert/strict';
import { SoftVoiceWorld } from '../src/world.js';
import { validateConfigPatch } from '../src/config.js';
import { SoftVoiceRuntime } from '../src/runtime.js';
import { mkdtempSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

function fixture(){
  const w=new SoftVoiceWorld({cfg:{},dataDir:'.'});w.active=true;w.speechEnabled=true;w.accepting=true;
  w.writeSettings=value=>{w.settings=value;};w.opts.persist=()=>{};
  const events=[];w.runtime={devices:async()=>({devices:[{name:'AMD',kind:'integrated'},{name:'NVIDIA',kind:'discrete'}]}),status:()=>({phase:'ready'}),history:[],stop:async()=>events.push('stop')};
  w.setSpeechEnabled=async enabled=>{w.speechEnabled=enabled;events.push(enabled?'start':'stop');};
  return {w,events};
}
test('explicit discrete hot switch stops the old worker and preserves other preferences',async()=>{
  const {w,events}=fixture();w.opts.cfg.syncBubbles=false;w.opts.cfg.volume=27;
  await w.selectDevice('NVIDIA');assert.deepEqual(events,['stop','start']);
  assert.equal(w.opts.cfg.deviceName,'NVIDIA');assert.equal(w.opts.cfg.syncBubbles,false);assert.equal(w.opts.cfg.volume,27);assert.equal(w.switchingDevice,false);
});
test('busy or absent GPU cannot trigger a device switch',async()=>{
  const {w,events}=fixture();w.speaking=true;await assert.rejects(w.selectDevice('NVIDIA'),/等当前/);w.speaking=false;
  await assert.rejects(w.selectDevice('Missing'),/设备不存在/);assert.deepEqual(events,[]);
});
test('failed GPU initialization restores the previous choice and enabled state',async()=>{
  const {w}=fixture();w.opts.cfg.deviceName='AMD';
  w.setSpeechEnabled=async enabled=>{w.speechEnabled=enabled;if(enabled&&w.opts.cfg.deviceName==='NVIDIA')throw Error('GPU unavailable');};
  await assert.rejects(w.selectDevice('NVIDIA'),/已恢复原设备配置/);assert.equal(w.opts.cfg.deviceName,'AMD');assert.equal(w.speechEnabled,true);
});
test('playback choices are validated and device changes cannot bypass reload',()=>{
  assert.equal(validateConfigPatch({playbackMode:'buffered'}).playbackMode,'buffered');
  assert.throws(()=>validateConfigPatch({playbackMode:'fake'}));
  const {w}=fixture();assert.throws(()=>w.saveConfig({deviceName:'NVIDIA'}),/设备选择/);
});
test('code update restores the prior speech choice even after update failure',async()=>{
  const {w,events}=fixture();w.opts.botDir='C:/Apps/Coopanion/data/home/companion';
  w.updates={status:()=>({busy:false}),run:async()=>{throw Error('checksum mismatch');}};
  await assert.rejects(w.applyUpdate(),/checksum/);assert.deepEqual(events,['stop','start']);assert.equal(w.speechEnabled,true);assert.equal(w.updating,false);
});

test('failed termination retains the worker and prevents loading a second model',async()=>{
  const dir=mkdtempSync(join(tmpdir(),'voice-termination-'));
  try {
    const r=new SoftVoiceRuntime({cfg:{},log:{},dataDir:dir}),child={pid:123};r.worker=child;
    r.terminateWorker=async()=>{throw Error('old worker is alive');};
    let starts=0;r.startWorker=async()=>{starts++;};
    await assert.rejects(r.stop(),/still|alive/);assert.equal(r.worker,child);assert.equal(r.state.phase,'error');
    await assert.rejects(r.ensure(),/alive/);assert.equal(starts,0);assert.equal(r.worker,child);
  } finally {rmSync(dir,{recursive:true,force:true});}
});

test('normal stop clears the worker only after termination and leaves no error banner',async()=>{
  const dir=mkdtempSync(join(tmpdir(),'voice-termination-'));
  try {
    const r=new SoftVoiceRuntime({cfg:{},log:{},dataDir:dir}),child={pid:123};r.worker=child;
    let done;r.terminateWorker=()=>new Promise(resolve=>{done=resolve;});
    const stopped=r.stop();assert.equal(r.worker,child);assert.equal(r.state.phase,'stopping');done();await stopped;
    assert.equal(r.worker,null);assert.equal(r.workerError,null);assert.equal(r.state.phase,'stopped');
  } finally {rmSync(dir,{recursive:true,force:true});}
});
