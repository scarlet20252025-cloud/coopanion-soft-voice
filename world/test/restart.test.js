import test from 'node:test';
import assert from 'node:assert/strict';
import {restartRequest} from '../src/restart.js';
import {SoftVoiceWorld} from '../src/world.js';

test('supervised restart writes the official request before scheduling graceful shutdown',async()=>{
 const order=[];let stop;
 const restart=restartRequest('fixture',{hosted:()=>true,loadBoot:async()=>({isSupervised:()=>true,requestRestart:dir=>order.push(dir)}),signal:()=>order.push('SIGTERM'),schedule:fn=>{stop=fn;}});
 assert.equal((await restart()).requested,true);assert.deepEqual(order,['fixture']);stop();assert.deepEqual(order,['fixture','SIGTERM']);
});
test('unsupported hosts never shutdown',async()=>{
 let stopped=false;const restart=restartRequest('fixture',{hosted:()=>false,signal:()=>{stopped=true;}});await assert.rejects(restart(),/不支持/);assert.equal(stopped,false);
});
test('panel restart requires explicit confirmation and a completed pending update',async()=>{
 const w=new SoftVoiceWorld({cfg:{},dataDir:'.',requestDesktopRestart:async()=>({requested:true})});w.runtime={status:()=>({})};w.updates={status:()=>({requiresRestart:true,busy:false})};
 const invoke=w.webUi().invoke;await assert.rejects(invoke('controls','restartDesktop',[]),/确认/);assert.equal((await invoke('controls','restartDesktop',[true])).requested,true);
 w.updates={status:()=>({requiresRestart:true,busy:true})};await assert.rejects(invoke('controls','restartDesktop',[true]),/正在执行/);
});
