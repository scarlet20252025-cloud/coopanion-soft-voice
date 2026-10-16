import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,mkdirSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { SoftVoiceRuntime } from '../src/runtime.js';
import { deviceChoice } from '../src/deployment.js';

const gtx={name:'NVIDIA GeForce GTX 1660',kind:'discrete',vendorId:4318};
const uhd={name:'Intel(R) UHD Graphics 630',kind:'integrated',vendorId:32902};

test('a machine without an integrated GPU must be asked, not guessed',()=>{
  const choice=deviceChoice([gtx]);
  assert.equal(choice.choose,true);
  assert.deepEqual(choice.devices,[gtx]);
  assert.match(choice.detail,/没有核显/);
  assert.match(choice.detail,/独显/);
  assert.equal(choice.device,undefined);
  // Naming the discrete GPU is the only way it is ever used.
  assert.deepEqual(deviceChoice([gtx],gtx.name),{device:gtx.name});
});

test('multiple integrated GPUs require a choice while a single one stays automatic',()=>{
  const other={name:'Intel(R) UHD Graphics 770',kind:'integrated',vendorId:32902};
  const ambiguous=deviceChoice([uhd,other]);
  assert.equal(ambiguous.choose,true);
  assert.match(ambiguous.detail,/多个核显/);
  assert.deepEqual(deviceChoice([uhd]),{device:''});
  assert.deepEqual(deviceChoice([uhd,gtx]),{device:''});
});

test('no Vulkan GPU at all reports the driver instead of an empty device list',()=>{
  const choice=deviceChoice([]);
  assert.match(choice.error,/驱动/);
  assert.equal(choice.choose,undefined);
});

test('the shipped client asks the user to confirm the chosen device',async()=>{
  const {readFileSync}=await import('node:fs');
  const meta=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8'));
  const source=readFileSync(new URL('../'+meta.cortico.consoleClient,import.meta.url),'utf8');
  assert.match(source,/deployDevice\.hidden=task\.phase!=='choose_device'/);
  assert.match(source,/task\.phase==='choose_device'\?'使用所选设备继续部署'/);
});

test('deployment checks model files even with speech off, and distinguishes runtime connection',()=>{
  const dir=mkdtempSync(join(tmpdir(),'voice-deployment-'));
  try {
    const r=new SoftVoiceRuntime({cfg:{},log:{},dataDir:dir}),base=join(dir,'runtime');mkdirSync(base);
    assert.equal(r.deploymentStatus().state,'missing');
    const python=join(base,'python.exe');writeFileSync(python,'stub');
    writeFileSync(join(r.root,'runtime-profile.json'),JSON.stringify({python,runtime:base,mode:'igpu'}));
    const cfg={dll:'engine.dll',model:'model.gguf',codec:'codec.gguf',speechOnly:{format:1}};
    writeFileSync(join(base,'native-runtime.json'),JSON.stringify(cfg));
    for(const name of ['engine.dll','model.gguf','codec.gguf','voice-features.json'])writeFileSync(join(base,name),'stub');
    r.stage('disabled','语音关闭');assert.equal(r.deploymentStatus().state,'installed');assert.equal(r.deploymentStatus().connected,false);
    r.worker={pid:1};r.stage('ready','就绪');assert.equal(r.deploymentStatus().state,'connected');
    r.stage('sleeping','休眠');assert.equal(r.deploymentStatus().state,'sleeping');assert.equal(r.deploymentStatus().installed,true);
    r.stage('waiting_memory','内存不足');assert.equal(r.deploymentStatus().state,'waiting_memory');
    writeFileSync(join(base,'model.gguf'),'');assert.equal(r.deploymentStatus().state,'missing');assert.equal(r.hasLocalFiles(),false);
    writeFileSync(join(base,'model.gguf'),'stub');r.stage('error','加载失败');assert.equal(r.deploymentStatus().state,'error');
    r.worker=null;r.stage('ready','过期状态');assert.equal(r.deploymentStatus().connected,false);
  } finally {rmSync(dir,{recursive:true});}
});
