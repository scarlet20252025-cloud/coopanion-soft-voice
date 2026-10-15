import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pythonJson } from './helpers.js';

const WORLD_VERSION=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8')).version;
const busyStages=new Set(['checking','downloading','validating','backing_up','installing','verifying','restoring']);
export class VoiceUpdates {
  constructor(runtime){this.runtime=runtime;this.state={stage:'idle',detail:'按需核对 GitHub 与 npm 版本',loadedWorldVersion:WORLD_VERSION};}
  status(){return {...this.state,busy:!!this.running||busyStages.has(this.state.stage)};}
  async run(action,extensions){
    if(this.running)throw new Error('已有更新操作正在执行');
    const p=this.runtime.profile();
    this.state={...this.state,stage:'checking',detail:'正在核对 GitHub 与 npm…',error:null};
    const args=[action,'--runtime',p.runtime,...(extensions?['--extensions',extensions]:[])];
    this.running=pythonJson(p,'coopanion_soft_voice.updates',args,msg=>{
      const pending=this.state.requiresRestart===true;
      this.state={...this.state,...msg};
      if(msg.currentWorldVersion)this.state.requiresRestart=pending||msg.currentWorldVersion!==WORLD_VERSION;
      if(msg.stage==='installed'){this.state.currentVersion=msg.version;this.state.available=false;this.state.requiresRestart=pending||msg.requiresRestart||msg.worldVersion!==WORLD_VERSION;}
    })
      .catch(err=>{this.state={...this.state,stage:'error',detail:err.message,error:err.message};throw err;})
      .finally(()=>{this.running=null;});
    return this.running;
  }
}
