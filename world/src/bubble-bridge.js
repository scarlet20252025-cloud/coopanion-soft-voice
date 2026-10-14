import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {pathToFileURL} from 'node:url';
const PATH='/api/soft-voice/bubble-sync';

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
  if(JSON.parse(readFileSync(join(root,'package.json'),'utf8')).version!=='0.1.4')throw Error('当前桌宠版本尚未验证气泡适配桥');
  if(!readFileSync(join(root,'web/pet-app.js'),'utf8').includes('SOFT_VOICE_BUBBLE_BRIDGE'))throw Error('尚未安装气泡显示适配，请运行气泡同步安装脚本');
  const {PetServer}=await import(pathToFileURL(join(dirname(entry),'server.ts')).href);
  return attachBubbleRoutes(PetServer,owner);
}
