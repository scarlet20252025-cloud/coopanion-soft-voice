import test from 'node:test';
import assert from 'node:assert/strict';
import {VoiceReports} from '../src/reports.js';
import {SoftVoiceRuntime} from '../src/runtime.js';

test('automatic reports require the option, repeated performance evidence and cooldown',async()=>{
  const cfg={autoDiagnostics:false,autoSubmitIssues:false},r=new VoiceReports({},cfg,{}),calls=[];
  r.run=async(...args)=>{calls.push(args);};
  r.observe({code:'worker_error'},1e12);assert.equal(calls.length,0);cfg.autoDiagnostics=true;
  const slow={type:'playback',seconds:5,totalSynthesisMs:9000,underrunMs:0,deviceUnderflows:0};
  r.observe(slow,1e12);assert.equal(calls.length,0);r.observe(slow,1e12+1);assert.equal(calls.length,1);
  r.observe(slow,1e12+3600001);assert.equal(calls.length,1);r.observe({code:'worker_error'},1e12+3600002);assert.equal(calls.length,2);
});
test('automatic local capture never submits unless the independent option is enabled',async()=>{
  for(const submit of [false,true]){
    const r=new VoiceReports({}, {autoSubmitIssues:submit},{}),calls=[];
    r.call=async(action,args)=>{calls.push(action);return action==='collect'?{report:{id:'a',code:'worker_error'}}:action==='list'?{reports:[]}:{};};
    await r.run('collect',[],true);assert.equal(calls.includes('submit'),submit);assert.equal(r.status().busy,false);
  }
});
test('user stop does not create an automatic fault report and observer errors cannot break worker replies',()=>{
  const r=Object.create(SoftVoiceRuntime.prototype);r.pending=new Map();let calls=0;
  r.onDiagnosticEvent=()=>{calls++;throw new Error('reporter offline');};
  r.fail(new Error('语音已停止'),null);assert.equal(calls,0);
  r.message({type:'done',id:'s',seconds:5,totalSynthesisMs:2000});assert.equal(r.state.phase,'ready');assert.equal(calls,1);
});
test('expected loading guard is recorded locally without automatic bug submission',async()=>{
  const r=new VoiceReports({}, {autoSubmitIssues:true},{}),calls=[];
  r.call=async(action)=>{calls.push(action);return action==='collect'?{report:{id:'a',code:'memory_guard'}}:{reports:[]};};
  await r.run('collect',[],true);assert.equal(calls.includes('submit'),false);
});
