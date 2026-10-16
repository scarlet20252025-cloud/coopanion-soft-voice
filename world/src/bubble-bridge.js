import {createRequire} from 'node:module';
import {existsSync, readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';
const PATH='/api/soft-voice/bubble-sync';
const MARKER='SOFT_VOICE_BUBBLE_BRIDGE';
// The pet version is not the contract; these call sites are. A pet release that
// already ships them needs no patching, and a pin on one version turns a working
// upstream integration into "缺少显示适配桥".
const CALLS=['voiceBubbleSync?.register(','voiceBubbleSync?.hold(','voiceBubbleSync?.shown(','voiceBubbleSync?.closed('];

/** null when the pet page can drive this extension; otherwise a user-facing reason. */
export function bridgeProblem(page,clientExists) {
  if(!page.includes(MARKER))return '尚未安装气泡显示适配，请按安装教程运行气泡同步脚本后重启桌宠';
  if(!clientExists)return '气泡显示适配缺少浏览器端脚本，请重新运行气泡同步脚本后重启桌宠';
  if(CALLS.some(call=>!page.includes(call)))return '桌宠的气泡显示适配与当前扩展不匹配，请重新运行气泡同步脚本后重启桌宠';
  return null;
}

function send(res,status,value){res.writeHead(status,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify(value));}
async function body(req){let size=0,parts=[];for await(const chunk of req){const bytes=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);size+=bytes.length;if(size>65536)throw Error('body too large');parts.push(bytes);}return JSON.parse(Buffer.concat(parts).toString('utf8'));}

/** Small same-origin adapter: no credentials, tools or desktop input are exposed. */
export function attachBubbleRoutes(Server,owner) {
  const previous=Server.prototype.handle;
  const wrapped=async function(req,res){
    const path=(req.url||'').split('?')[0];
    if(path!==PATH)return previous.call(this,req,res);
    if(!this.allowed(req,req.method!=='GET')){res.writeHead(421).end();return;}
    if(req.method==='GET'){send(res,200,owner.bubbleSync.snapshot());return;}
    if(req.method!=='POST'){send(res,405,{error:'method not allowed'});return;}
    try{
      const msg=await body(req);
      if(typeof msg.id!=='string'||!msg.id||msg.id.length>128)throw Error('invalid bubble id');
      if(msg.action==='register'){
        if(typeof msg.text!=='string'||msg.text.length>16000)throw Error('invalid bubble text');
        owner.bubbleSync.register(msg.id,msg.text);
      }else if(msg.action==='shown')owner.bubbleSync.shown(msg.id);
      else if(msg.action==='closed')owner.bubbleSync.closed(msg.id);
      else throw Error('unknown action');
      send(res,200,owner.bubbleSync.snapshot());
    }catch{send(res,400,{error:'invalid bubble sync message'});}
  };
  Server.prototype.handle=wrapped;
  return ()=>{if(Server.prototype.handle===wrapped)Server.prototype.handle=previous;};
}

export async function installBubbleBridge(owner) {
  const {repoRoot}=await import('cortico/paths.ts');
  const require=createRequire(join(repoRoot(),'package.json'));
  const entry=require.resolve('cortico-world-desktop-pet');
  const root=dirname(dirname(entry));
  const problem=bridgeProblem(readFileSync(join(root,'web/pet-app.js'),'utf8'),existsSync(join(root,'web/soft-voice-bubble-sync.js')));
  if(problem)throw Error(problem);
  const {PetServer}=await import(pathToFileURL(join(dirname(entry),'server.ts')).href);
  return attachBubbleRoutes(PetServer,owner);
}
