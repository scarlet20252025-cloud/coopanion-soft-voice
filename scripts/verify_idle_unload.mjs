// Opt-in live worker check: plays one sentence, uses isolated World settings.
import {SoftVoiceWorld} from '../world/src/world.js';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {execFileSync} from 'node:child_process';
const [profileFile,output]=process.argv.slice(2);
if(!profileFile||!output)throw new Error('Usage: node scripts/verify_idle_unload.mjs runtime-profile.json output.json');
const data=resolve('.runtime/idle-check-'+Date.now()),root=join(data,'soft-voice');
mkdirSync(root,{recursive:true});
writeFileSync(join(root,'runtime-profile.json'),readFileSync(profileFile));
const light=process.argv[4]==='light';
writeFileSync(join(root,'settings.json'),JSON.stringify({speechEnabled:true,config:{idleUnloadSec:5,keepWorker:light}}));
const w=new SoftVoiceWorld({cfg:{},dataDir:data});
const wait=async predicate=>{const start=Date.now();while(!predicate()){if(Date.now()-start>120000)throw new Error('Timeout');await new Promise(r=>setTimeout(r,100));}};
const ids=pid=>JSON.parse(execFileSync('powershell.exe',['-NoProfile','-Command',`$ids=@(${pid}); $ids+=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=${pid}" | Select-Object -ExpandProperty ProcessId); ConvertTo-Json -InputObject @($ids)`],{encoding:'utf8',windowsHide:true}));
const report={};
try {
  await w.start({log:{info:()=>{},warn:console.error}});
  await wait(()=>w.accepting);
  report.workerIds=ids(w.runtime.worker.pid);
  report.initialLoadMs=w.runtime.loadMs;
  const memory=()=>JSON.parse(execFileSync('powershell.exe',['-NoProfile','-Command',`ConvertTo-Json -InputObject @(Get-Process -Id ${report.workerIds.join(',')} -ErrorAction SilentlyContinue | Select-Object Id,PrivateMemorySize64,WorkingSet64)`],{encoding:'utf8',windowsHide:true}));
  report.loadedMemory=memory();
  await wait(()=>w.runtime.status().phase==='sleeping');
  report.sleeping=w.status();
  report.sleepingMemory=memory();
  report.remainingWorkerIds=JSON.parse(execFileSync('powershell.exe',['-NoProfile','-Command',`ConvertTo-Json -InputObject @(Get-Process -Id ${report.workerIds.join(',')} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)`],{encoding:'utf8',windowsHide:true}));
  const started=Date.now();
  w.onToolCall({tool:'pet_say',mod:'desktop-pet',run:'idle-verification',seq:1,args:{script:'我在这里陪你呀，慢慢来，不着急。'}});
  await w.draining;
  report.wakeAndPlaybackMs=Date.now()-started;
  report.afterWake=w.status();
  if(light){
    await wait(()=>w.runtime.status().phase==='sleeping');
    report.sleepingAfterSpeechMemory=memory();
    w.onToolCall({tool:'pet_say',mod:'desktop-pet',run:'idle-verification',seq:2,args:{script:'我在这里陪你呀，慢慢来，不着急。'}});
    await w.draining;
    report.secondWake=w.status();
  }
  if((!light&&report.remainingWorkerIds.length)||(light&&!report.remainingWorkerIds.length)||w.blocked||!w.runtime.lastSpeech)throw new Error('Unload/wake check failed');
} finally {
  await w.stop();
  writeFileSync(output,JSON.stringify(report,null,2));
}
console.log(JSON.stringify({initialLoadMs:report.initialLoadMs,remainingWorkerIds:report.remainingWorkerIds,
  wakeAndPlaybackMs:report.wakeAndPlaybackMs,lastSpeech:report.afterWake.lastSpeech}));
