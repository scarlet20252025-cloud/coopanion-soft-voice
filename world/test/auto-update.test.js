import test from 'node:test';
import assert from 'node:assert/strict';
import {SoftVoiceWorld} from '../src/world.js';

function fixture(){
 const w=new SoftVoiceWorld({cfg:{autoCheckUpdates:true},dataDir:'.',botDir:'fixture'});w.active=true;w.nextUpdateCheck=0;
 const state={available:true,supported:true};let checks=0,applies=0;
 w.updates={status:()=>state,run:async()=>{checks++;}};
 w.applyUpdate=async()=>{applies++;state.available=false;};
 return{w,state,counts:()=>({checks,applies})};
}
test('automatic checks are daily and do not install by default',async()=>{
 const {w,counts}=fixture();await w.maybeUpdates(100);await w.maybeUpdates(200);assert.deepEqual(counts(),{checks:1,applies:0});
});
test('available updates remain prompts and never install automatically',async()=>{
 const {w,counts}=fixture();await w.maybeUpdates(100);await w.maybeUpdates(86400200);assert.deepEqual(counts(),{checks:2,applies:0});
});
test('disabled checks, failed checks and shutdown do not retry each tick',async()=>{
 const {w,counts}=fixture();w.opts.cfg.autoCheckUpdates=false;await w.maybeUpdates(100);assert.equal(counts().checks,0);
 w.opts.cfg.autoCheckUpdates=true;let failures=0;w.updates.run=async()=>{failures++;throw Error('offline');};await w.maybeUpdates(200);await w.maybeUpdates(300);assert.equal(failures,1);
 w.active=false;await w.maybeUpdates(3600200);assert.equal(failures,1);assert.equal(counts().applies,0);
});
