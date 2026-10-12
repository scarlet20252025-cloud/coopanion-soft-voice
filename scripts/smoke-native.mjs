// Explicitly opted-in, zero-amplitude Node -> plugin -> iGPU -> Windows test.
import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {readFileSync,writeFileSync} from 'node:fs';
const [pluginArg,reportArg]=process.argv.slice(2);
if(!pluginArg || !reportArg) throw new Error('Usage: node smoke-native.mjs ISOLATED_PLUGIN REPORT');
const plugin=resolve(pluginArg);
const profile=JSON.parse(readFileSync(join(plugin,'.cosyvoice-tts/softvoice-profile.json'),'utf8'));
if(profile.mode!=='igpu') throw new Error('This test requires the explicit iGPU profile');
const {CosyRuntime}=await import(pathToFileURL(join(plugin,'src/runtime.js')).href);
const settings=JSON.parse(readFileSync(join(plugin,'.cosyvoice-tts/settings.json'),'utf8'));
const runtime=new CosyRuntime({cfg:{...settings.config,volume:0},log:{info(){},warn:console.error}});
const deadline=setTimeout(()=>{runtime.stop();process.exitCode=1;},90000);
try {
  const start=performance.now();
  await runtime.ensure();
  const readyMs=Math.round(performance.now()-start);
  const results=[];
  for(const text of ['我会乖乖等你。','今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？']) {
    results.push(await runtime.speak(text));
  }
  const status=runtime.status();
  const report={backend:'igpu',silent:true,readyMs,results,modelReady:status.modelReady,lastError:status.lastError??null};
  writeFileSync(resolve(reportArg),JSON.stringify(report,null,2));
  if(status.lastError || !status.modelReady || results.some(x=>x.skipped || x.underrunMs>0 || x.deviceUnderflows>0)) {
    throw new Error(JSON.stringify(report));
  }
  console.log(JSON.stringify(report));
} finally {clearTimeout(deadline);await runtime.stop();}
