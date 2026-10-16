import { createHash } from 'node:crypto';
import { createReadStream, existsSync } from 'node:fs';
import { mkdir, open, readFile, rename, rm, stat, statfs, writeFile, copyFile } from 'node:fs/promises';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { spawn } from 'node:child_process';
import { BUNDLE } from './deployment-manifest.js';

export async function sha256(file) {
  const hash=createHash('sha256');for await(const chunk of createReadStream(file))hash.update(chunk);return hash.digest('hex');
}
export function sourceList(bundle,choice='auto') {
  if(!['auto','domestic','github'].includes(choice))throw Error('未知下载源');
  const sources=bundle.sources.filter(s=>choice==='auto'||s.id===choice);
  if(!sources.length)throw Error('所选下载源尚未配置');
  return sources;
}
export function resumeOffset(response,offset,total) {
  if(response.status===200)return 0;
  const match=/^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range')||'');
  if(response.status!==206||!match||Number(match[1])!==offset||Number(match[3])!==total||Number(match[2])>=total)throw Error('下载服务器返回的续传范围不正确');
  return offset;
}
export async function downloadBundle(bundle,archive,choice,signal,progress,fetcher=fetch) {
  if(existsSync(archive)&&await sha256(archive)===bundle.sha256)return;
  const partial=archive+'.partial';let failures=[];
  for(const source of sourceList(bundle,choice)) {
    signal.throwIfAborted();
    try {
      let offset=existsSync(partial)?(await stat(partial)).size:0;
      if(offset>=bundle.bytes){if(offset===bundle.bytes&&await sha256(partial)===bundle.sha256){await rename(partial,archive);return;}await rm(partial,{force:true});offset=0;}
      const controller=new AbortController();const combined=AbortSignal.any([signal,controller.signal]);
      let timer=setTimeout(()=>controller.abort(Error('下载连接超时')),30000);
      let response;
      try {response=await fetcher(source.url,{headers:offset?{Range:`bytes=${offset}-`}:{},signal:combined});} finally {clearTimeout(timer);}
      if(!response.ok||!response.body)throw Error(`下载源返回 HTTP ${response.status}`);
      offset=resumeOffset(response,offset,bundle.bytes);
      const file=await open(partial,offset?'a':'w');const reader=response.body.getReader();let received=offset;const started=Date.now();
      try {
        while(true){
          signal.throwIfAborted();timer=setTimeout(()=>controller.abort(Error('下载长时间无响应')),30000);
          let part;try{part=await reader.read();}finally{clearTimeout(timer);}
          if(part.done)break;
          received+=part.value.length;if(received>bundle.bytes)throw Error('下载大小超过发布清单');
          let written=0;
          while(written<part.value.length){const result=await file.write(part.value,written,part.value.length-written);if(!result.bytesWritten)throw Error('磁盘写入未完成');written+=result.bytesWritten;}
          progress({phase:'downloading',detail:'正在下载模型与运行环境',source:source.label,received,total:bundle.bytes,percent:Math.floor(received/bundle.bytes*100),bytesPerSecond:Math.round((received-offset)/Math.max(1,(Date.now()-started)/1000))});
        }
      } finally {await file.close();await reader.cancel().catch(()=>{});}
      if(received!==bundle.bytes)throw Error('下载中断，已保留续传文件');
      progress({phase:'validating',detail:'正在校验完整包 SHA256',percent:null});
      if(await sha256(partial)!==bundle.sha256){await rm(partial,{force:true});throw Error('文件校验失败，已移除损坏下载');}
      await rename(partial,archive);return;
    }catch(error){if(signal.aborted)throw signal.reason;failures.push(`${source.label}：${error.message}`);progress({phase:'retrying',detail:failures.at(-1)+'；尝试下一下载源',percent:null});}
  }
  throw Error(failures.join('；'));
}
function command(exe,args,signal,extraEnv={}) {
  return new Promise((resolve,reject)=>{
    const child=spawn(exe,args,{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',...extraEnv},signal});let tail='';
    child.stdout.on('data',b=>{tail=(tail+b.toString('utf8')).slice(-12000);});child.stderr.on('data',b=>{tail=(tail+b.toString('utf8')).slice(-12000);});
    child.on('error',reject);child.on('close',code=>code===0?resolve(tail):reject(Error(tail||`安装进程退出 (${code})`)));
  });
}
const EXTRACT=`$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::OpenRead($env:VOICE_DEPLOY_ZIP)
try {
 $root=[IO.Path]::GetFullPath($env:VOICE_DEPLOY_DIR)+[IO.Path]::DirectorySeparatorChar
 foreach($entry in $zip.Entries) {
  $target=[IO.Path]::GetFullPath([IO.Path]::Combine($root,$entry.FullName))
  if(-not $target.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) -or $entry.FullName.Contains(':')) {throw 'Unsafe archive path'}
 }
} finally {$zip.Dispose()}
[IO.Compression.ZipFile]::ExtractToDirectory($env:VOICE_DEPLOY_ZIP,$env:VOICE_DEPLOY_DIR)`;
// Pure decision so the discrete-only path stays testable without spawning the
// installer. A discrete GPU is never selected implicitly: it shares VRAM with
// games, so the user must name the device.
export function deviceChoice(inventory,deviceName='') {
  if(!inventory.length)return {error:'没有检测到可用的 Vulkan 显卡。请安装显卡驱动后重试。'};
  if(deviceName)return {device:deviceName};
  const integrated=inventory.filter(d=>d.kind==='integrated');
  if(integrated.length===1)return {device:''};
  return {choose:true,devices:inventory,
    detail:integrated.length===0?
      '这台电脑没有核显。请在下面选择要使用的独显，然后再次点击部署按钮继续（模型已下载，不会重复下载）。':
      '检测到多个核显。请在下面选择要使用的设备，然后再次点击部署按钮继续（模型已下载，不会重复下载）。'};
}
export class VoiceDeployment {
  constructor(runtime,{bundle=BUNDLE,fetcher=fetch}={}){this.runtime=runtime;this.bundle=bundle;this.fetcher=fetcher;this.state={phase:'idle',detail:'可在此下载并部署定制模型',sources:bundle.sources.map(({id,label})=>({id,label})),bytes:bundle.bytes};}
  status(){return {...this.state,busy:!!this.running};}
  update(value){Object.assign(this.state,value);}
  cancel(){this.controller?.abort(Error('已取消部署，下载文件保留供下次续传'));}
  start(options={}) {
    if(this.running)throw Error('模型部署正在进行');
    if(process.platform!=='win32'||process.arch!=='x64')throw Error('当前一键部署仅支持 Windows x64');
    this.controller=new AbortController();this.update({phase:'preparing',detail:'正在检查已有资源和磁盘空间',error:null,percent:null});
    this.running=this.install(options,this.controller.signal).catch(error=>{this.update({phase:this.controller.signal.aborted?'cancelled':'error',detail:error.message,error:error.message,percent:null});}).finally(()=>{this.running=null;});
    return this.status();
  }
  async install({source='auto',offlinePath='',deviceName=''}={},signal) {
    if(this.runtime.hasLocalFiles()){this.update({phase:'installed',detail:'已检测到有效部署，保留现有模型、运行时和扩展',percent:100});return;}
    const base=join(this.runtime.root,'deployment');await mkdir(base,{recursive:true});
    const archive=join(base,this.bundle.file),target=join(base,'runtime-'+this.bundle.version);
    const disk=await statfs(base),required=(existsSync(archive)?0:this.bundle.bytes)+(existsSync(join(target,'portable-manifest.json'))?0:1.5*1024**3)+256*1024**2;
    if(disk.bavail*disk.bsize<required)throw Error('空闲磁盘不足，当前部署约需 '+(required/1024**3).toFixed(1)+' GiB');
    if(offlinePath){
      if(typeof offlinePath!=='string'||!isAbsolute(offlinePath))throw Error('请选择完整安装 ZIP 的绝对路径');
      this.update({phase:'validating',detail:'正在校验离线安装包',percent:null});
      if((await stat(offlinePath)).size!==this.bundle.bytes||await sha256(offlinePath)!==this.bundle.sha256)throw Error('离线包版本或 SHA256 不匹配，请使用本页指定版本');
      if(resolve(offlinePath)!==resolve(archive))await copyFile(offlinePath,archive);
    }else await downloadBundle(this.bundle,archive,source,signal,s=>this.update(s),this.fetcher);
    signal.throwIfAborted();
    if(!existsSync(join(target,'portable-manifest.json'))){
      const staging=join(base,'extract-'+Date.now());this.update({phase:'extracting',detail:'正在解压模型与运行环境',percent:null});
      try {await command('powershell.exe',['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(EXTRACT,'utf16le').toString('base64')],signal,{VOICE_DEPLOY_ZIP:archive,VOICE_DEPLOY_DIR:staging});await rename(staging,target);}
      finally {const rel=relative(base,staging);if(rel&&!rel.startsWith('..')&&!isAbsolute(rel))await rm(staging,{recursive:true,force:true});}
    }
    const meta=JSON.parse(await readFile(join(target,'portable-manifest.json'),'utf8'));
    if(meta.version!==this.bundle.version)throw Error('解压后的运行时版本不一致');
    const python=join(target,'python','python.exe');
    this.update({phase:'configuring',detail:'正在检测 Vulkan 设备并生成本机配置',percent:null});
    const inventory=JSON.parse((await command(python,['-m','coopanion_soft_voice.cli','--runtime',target,'devices'],signal)).trim()).devices;
    const choice=deviceChoice(inventory,deviceName);
    if(choice.error)throw Error(choice.error);
    // The archive and extracted runtime are reused, so confirming only repeats the rest.
    if(choice.choose){this.update({phase:'choose_device',detail:choice.detail,devices:choice.devices,percent:null});return;}
    await command(python,[join(target,'scripts','activate_portable.py'),'--root',target,...(choice.device?['--device-name',choice.device]:[])],signal);
    const profile=join(this.runtime.root,'runtime-profile.json');
    this.update({phase:'testing',detail:'正在实际合成并静音测试音频；不会播放测试声音。首次运行需要编译显卡着色器，独显上可能多等 20–30 秒，之后不再需要。',percent:null});
    let waiting=false;
    try {await command(python,[join(target,'scripts','verify_deployment.py'),'--runtime',target,'--output',join(target,'verification'),...(deviceName?['--device-name',deviceName]:[])],signal);}
    catch(error){if(signal.aborted)throw error;if(/GiB free RAM|keeping text only/.test(error.message))waiting=true;else throw error;}
    signal.throwIfAborted();
    if(existsSync(profile))await copyFile(profile,profile+'.before-deploy-'+Date.now());
    await writeFile(profile+'.deploy-tmp',JSON.stringify({python,runtime:target,mode:'igpu'},null,2),'utf8');await rename(profile+'.deploy-tmp',profile);
    this.update({phase:waiting?'waiting_memory':'installed',detail:waiting?'模型安装完成，内存不足，暂未通过合成验收；释放内存后点击开启语音':'部署完成，真实合成与播放测试通过；点击开启语音即可使用',percent:100,runtimeVersion:meta.version});
  }
}
