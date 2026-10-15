import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,readFile,writeFile,rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import { downloadBundle,sourceList,VoiceDeployment } from '../src/deployment.js';
import { SoftVoiceWorld } from '../src/world.js';
const bytes=Buffer.from('verified model bundle'),sha256=createHash('sha256').update(bytes).digest('hex');
const bundle={file:'bundle.zip',version:'0.5.3',bytes:bytes.length,sha256,sources:[{id:'domestic',label:'国内',url:'https://domestic.test/file'},{id:'github',label:'GitHub',url:'https://github.test/file'}]};
async function temp(run){const dir=await mkdtemp(join(tmpdir(),'voice-deploy-'));try{await run(join(dir,'bundle.zip'));}finally{await rm(dir,{recursive:true,force:true});}}
test('deployment requires an explicit action; no network on creation',()=>{let called=false;const d=new VoiceDeployment({}, {bundle,fetcher:()=>{called=true;}});assert.equal(d.status().busy,false);assert.equal(called,false);assert.throws(()=>sourceList(bundle,'other'));});
test('download falls back and verifies exact bytes',()=>temp(async file=>{let calls=[];await downloadBundle(bundle,file,'auto',new AbortController().signal,()=>{},async url=>{calls.push(url);if(calls.length===1)throw Error('offline');return new Response(bytes);});assert.equal(calls.length,2);assert.deepEqual(await readFile(file),bytes);}));
test('partial file resumes only with a matching Content-Range',()=>temp(async file=>{await writeFile(file+'.partial',bytes.subarray(0,5));await downloadBundle(bundle,file,'domestic',new AbortController().signal,()=>{},async(url,opts)=>{assert.equal(opts.headers.Range,'bytes=5-');return new Response(bytes.subarray(5),{status:206,headers:{'content-range':`bytes 5-${bytes.length-1}/${bytes.length}`}});});assert.deepEqual(await readFile(file),bytes);}));
test('server ignoring range restarts rather than concatenating corrupt bytes',()=>temp(async file=>{await writeFile(file+'.partial',bytes.subarray(0,5));await downloadBundle(bundle,file,'domestic',new AbortController().signal,()=>{},async()=>new Response(bytes));assert.deepEqual(await readFile(file),bytes);}));
test('corrupt complete download is never installed',()=>temp(async file=>{await assert.rejects(downloadBundle(bundle,file,'domestic',new AbortController().signal,()=>{},async()=>new Response(Buffer.alloc(bytes.length))));assert.equal(existsSync(file),false);assert.equal(existsSync(file+'.partial'),false);}));
test('cancelled transfer retains partial bytes and can resume',()=>temp(async file=>{const c=new AbortController();await assert.rejects(downloadBundle(bundle,file,'domestic',c.signal,()=>c.abort(Error('cancel')),async()=>new Response(new ReadableStream({start(controller){controller.enqueue(bytes.subarray(0,5));controller.enqueue(bytes.subarray(5));controller.close();}}))));assert.deepEqual(await readFile(file+'.partial'),bytes.subarray(0,5));}));
test('verified cache avoids any download',()=>temp(async file=>{await writeFile(file,bytes);await downloadBundle(bundle,file,'auto',new AbortController().signal,()=>{},()=>{throw Error('network must not run');});}));

test('successful deployment persists the explicitly selected GPU without the hot-switch guard',async()=>{
  let persisted,settings;
  const w=new SoftVoiceWorld({cfg:{},persist:patch=>{persisted=patch;}});
  w.active=true;w.speechEnabled=false;w.assertIdleOperation=()=>{};
  w.writeSettings=value=>{settings=value;};
  w.runtime={stop:async()=>{},hasLocalFiles:()=>true};
  w.deployer={start(){this.running=Promise.resolve();return {phase:'preparing'};},status:()=>({phase:'installed'})};
  await w.startDeployment({deviceName:'Explicit NVIDIA'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(w.opts.cfg.deviceName,'Explicit NVIDIA');
  assert.equal(persisted.deviceName,'Explicit NVIDIA');
  assert.equal(settings.config.deviceName,'Explicit NVIDIA');
});
