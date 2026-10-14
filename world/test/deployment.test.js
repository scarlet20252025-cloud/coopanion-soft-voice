import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,mkdirSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { SoftVoiceRuntime } from '../src/runtime.js';

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
