import test from 'node:test';
import assert from 'node:assert/strict';
import { BubbleSpeechSync } from '../src/bubble-sync.js';
import { createVoiceBubbleSync } from '../src/bubble-client.js';
import { attachBubbleRoutes, bridgeProblem } from '../src/bubble-bridge.js';
import {Readable} from 'node:stream';

const item=(key,text='第一段。')=>({key,text});
test('bubble sync is gated on the pet hooks, not on one pet version',()=>{
  // Exactly what an upstream pet release that already ships the integration has.
  const shipped=['// SOFT_VOICE_BUBBLE_BRIDGE: all synchronization logic is in the extension client.',
    "case 'say': voiceBubbleSync?.register(m.id, m.beats);",
    'if (item?.kind === \'say\') voiceBubbleSync?.closed(item.id);',
    'const synced = voiceBubbleSync?.hold(it.id, it.i === it.beats.length - 1);',
    'if (it.i === 0) voiceBubbleSync?.shown(it.id);'].join('\n');
  assert.equal(bridgeProblem(shipped,true),null);
  assert.match(bridgeProblem('plain page',true),/尚未安装/);
  assert.match(bridgeProblem(shipped,false),/浏览器端脚本/);
  assert.match(bridgeProblem(shipped.replace('voiceBubbleSync?.hold(','hold('),true),/不匹配/);
});
test('audio completion, not elapsed bubble time, releases an utterance',async()=>{
 const gate=new BubbleSpeechSync(()=>true);gate.register('bubble-1','第一段。');gate.track(item('call-1'));
 let started=false;const waiting=gate.waitUntilShown('call-1').then(()=>started=true);
 await new Promise(r=>setTimeout(r,5));assert.equal(started,false);gate.shown('bubble-1');await waiting;
 assert.equal(gate.snapshot().bubbles[0].state,'playing');gate.finish('call-1');
 assert.equal(gate.snapshot().bubbles[0].state,'done');gate.closed('bubble-1');
 const b=gate.snapshot().bubbles[0];assert.ok(b.closedAt>=b.audioEndedAt);
});
test('identical consecutive phrases pair with distinct calls and bubble IDs',()=>{
 const gate=new BubbleSpeechSync(()=>true);gate.track(item('a'));gate.track(item('b'));gate.register('1','第一 段。');gate.register('2','第一段。');
 gate.finish('a');assert.deepEqual(gate.snapshot().bubbles.map(b=>b.state),['done','queued']);gate.finish('b','failed');assert.equal(gate.snapshot().bubbles[1].state,'failed');
});
test('stopping releases queued and playing bubble waits; disabled waits do not delay speech',async()=>{
 let enabled=true;const gate=new BubbleSpeechSync(()=>enabled);gate.track(item('a'));gate.register('1','第一段。');gate.cancelAll();
 assert.equal(gate.snapshot().bubbles[0].state,'cancelled');enabled=false;await gate.waitUntilShown('a');assert.equal(gate.snapshot().enabled,false);
});
test('pet client holds beyond its text timer and releases on actual playback receipt',async()=>{
 const gate=new BubbleSpeechSync(()=>true);gate.track(item('a'));
 const fetchImpl=async(_url,opt={})=>{if(opt.method==='POST'){const m=JSON.parse(opt.body);if(m.action==='register')gate.register(m.id,m.text);if(m.action==='shown')gate.shown(m.id);if(m.action==='closed')gate.closed(m.id);}return {ok:true,json:async()=>gate.snapshot()};};
 const ui=createVoiceBubbleSync({fetchImpl,interval:5});ui.register('1',[{text:'第一段。'}]);ui.shown('1');await new Promise(r=>setTimeout(r,10));
 assert.equal(ui.hold('1',true),true);assert.equal(ui.hold('1',false),undefined);
 gate.finish('a');await new Promise(r=>setTimeout(r,12));assert.equal(ui.hold('1',true),false);ui.closed('1');ui.dispose();
});
test('missing extension and safety timeout restore normal bubble timing',async()=>{
 let t=0;const ui=createVoiceBubbleSync({fetchImpl:async()=>{throw Error('offline')},now:()=>t,interval:2});ui.register('1',[{text:'a'}]);await new Promise(r=>setTimeout(r,10));assert.equal(ui.hold('1',true),undefined);ui.dispose();
});
test('same-origin bridge routes reject malformed requests and unhook cleanly',async()=>{
 class Server{allowed(req){return req.allowed!==false;}async handle(_req,res){res.original=true;}}
 const original=Server.prototype.handle,owner={bubbleSync:new BubbleSpeechSync(()=>true)},undo=attachBubbleRoutes(Server,owner),server=new Server();
 const req=(value,method='POST',path='/api/soft-voice/bubble-sync')=>Object.assign(Readable.from([JSON.stringify(value)]),{url:path,method});
 const response=()=>({writeHead(status){this.status=status;return this;},end(body){this.body=body;}});
 let res=response();await server.handle(req({action:'register',id:'1',text:'hello'}),res);assert.equal(res.status,200);
 res=response();await server.handle(req({action:'unknown',id:'1'}),res);assert.equal(res.status,400);
 res=response();await server.handle(Object.assign(req({} ,'GET'),{allowed:false}),res);assert.equal(res.status,421);
 res=response();await server.handle(req({},'GET','/api/other'),res);assert.equal(res.original,true);undo();assert.equal(Server.prototype.handle,original);
});
