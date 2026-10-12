// Real Node -> plugin -> installed Python -> Windows playback, with zero amplitude.
import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {readFileSync,writeFileSync} from 'node:fs';
const [pluginArg,reportArg]=process.argv.slice(2);
if(!pluginArg || !reportArg) throw new Error('Usage: node smoke-cache.mjs PLUGIN REPORT');
const plugin=resolve(pluginArg);
const profile=JSON.parse(readFileSync(join(plugin,'.cosyvoice-tts/softvoice-profile.json'),'utf8'));
if(profile.mode!=='cache') throw new Error('Refusing to start a model backend for this test');
const {CosyRuntime}=await import(pathToFileURL(join(plugin,'src/runtime.js')).href);
const settings=JSON.parse(readFileSync(join(plugin,'.cosyvoice-tts/settings.json'),'utf8'));
const runtime=new CosyRuntime({cfg:{...settings.config,volume:0},log:{info(){},warn:console.error}});
const started=performance.now();
const deadline=setTimeout(()=>{runtime.stop();process.exitCode=1;},30000);
try {
 await runtime.ensure();
 const readyMs=performance.now()-started;
 await runtime.speak('今天也辛苦啦，先休息一小会儿，我会乖乖等你。');
 const played=runtime.status().lastSpeech;
 const combined=await runtime.speak('今天也辛苦啦，先休息一小会儿，我会乖乖等你。\n今天也辛苦啦，先休息一小会儿，我会乖乖等你。');
 if(Math.abs(combined.seconds-9)>.001) throw new Error('Combined cached audio has wrong duration');
 const missed=await runtime.speak('This is intentionally not in the cache.');
 if(!missed.skipped || missed.reason!=='cache_miss') throw new Error('Cache miss did not stay silent');
 const status=runtime.status();
 const report={backend:profile.mode,readyMs:Math.round(readyMs),silent:true,
   lastSpeech:played,combinedSeconds:combined.seconds,cacheMissSkipped:missed.skipped,modelReady:status.modelReady,lastError:status.lastError??null,
   note:'Real plugin IPC and zero-amplitude Windows playback; no perceptual or game stability test'};
 if(status.lastError || !played || !status.modelReady) throw new Error(JSON.stringify(report));
 writeFileSync(resolve(reportArg),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
} finally {clearTimeout(deadline);await runtime.stop();}
