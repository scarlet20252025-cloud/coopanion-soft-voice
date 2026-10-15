"""Stage verified assets, then publish explicitly. No credentials are stored."""
import argparse,hashlib,http.client,json,os,subprocess,sys,urllib.parse,urllib.request
import re,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from coopanion_soft_voice.issue_reporting import credentials
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','publish','inspect']);p.add_argument('--directory',type=Path,required=True);p.add_argument('--notes',type=Path,required=True);a=p.parse_args()
REPO='scarlet20252025-cloud/coopanion-soft-voice';API='https://api.github.com/repos/'+REPO
folder=a.directory;report=json.loads((ROOT/'portable-release.json').read_text(encoding='utf-8'));update=json.loads((ROOT/'update-release.json').read_text(encoding='utf-8'))
version=report['version'];assert version==update['version']
if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid release version')
token=credentials()
if not token:raise RuntimeError('GitHub credentials unavailable; sign in yourself, never paste tokens into chat')
headers={'Authorization':'Bearer '+token,'User-Agent':'Asryto-verified-release','Accept':'application/vnd.github+json'}
opener=urllib.request.build_opener()
def api(route,method='GET',body=None):
 req=urllib.request.Request(API+route,data=json.dumps(body,ensure_ascii=False).encode('utf-8') if body is not None else None,headers={**headers,'Content-Type':'application/json'},method=method)
 with opener.open(req,timeout=60) as response:
  content=response.read();return json.loads(content) if content else None
commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
notes=a.notes.read_text(encoding='utf-8')
releases=api('/releases?per_page=100&verified='+str(time.time_ns()))
plan={'commit':commit,'version':version,'installerSha256':report['sha256'],'updateSha256':update['patch']['sha256']}
plan_file=folder/'release-stage.json'
if a.action=='publish' and (not plan_file.exists() or json.loads(plan_file.read_text(encoding='utf-8'))!=plan):
 raise RuntimeError('Prepare these exact assets and source commit before publishing')
def release(tag,technical=False):
 found=next((r for r in releases if r['tag_name']==tag),None)
 if found is None:
  asset=update['patch']['file'] if technical else report['file']
  expected_name=('程序内更新资源 ' if technical else '轻量化本地语音引擎 ')+tag+' · Asryto'
  candidates=[r for r in releases if r['draft'] and r['tag_name'].startswith('untagged-') and (r['name']==expected_name or any(v['name']==asset for v in r['assets']))]
  if len(candidates)>1:raise RuntimeError('Ambiguous draft release')
  if candidates:found=candidates[0]
 body='程序内代码更新资源，非首次安装包。完整安装请使用最新正式版。作者 Asryto。' if technical else notes
 if found:
  if a.action=='inspect':return found
  if not found['draft']:
   if a.action=='prepare':raise RuntimeError('Release is already public; refusing to replace published bytes: '+tag)
   return found
  return api('/releases/'+str(found['id']),'PATCH',{'tag_name':tag,'target_commitish':commit,'body':body})
 if a.action!='prepare':raise RuntimeError('Expected draft is missing: '+tag)
 return api('/releases','POST',{'tag_name':tag,'target_commitish':commit,'name':('程序内更新资源 ' if technical else '轻量化本地语音引擎 ')+tag+' · Asryto','draft':True,'prerelease':technical,'body':body})
def digest(file):
 h=hashlib.sha256()
 with file.open('rb') as f:
  for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
 return h.hexdigest()
def upload(release,file,sha):
 if digest(file)!=sha:raise RuntimeError('Local checksum mismatch')
 assets=api('/releases/'+str(release['id'])+'/assets');old=next((v for v in assets if v['name']==file.name),None)
 if old:
  if old['size']==file.stat().st_size and old.get('digest')=='sha256:'+sha:return old
  if not release['draft']:raise RuntimeError('Refusing to replace public asset')
  api('/releases/assets/'+str(old['id']),'DELETE')
 url=urllib.parse.urlsplit(release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(file.name))
 proxy=urllib.request.getproxies().get('https')
 if proxy:
  pr=urllib.parse.urlsplit(proxy)
  if pr.username:raise RuntimeError('Authenticated upload proxy is not supported')
  conn=http.client.HTTPSConnection(pr.hostname,pr.port or 80,timeout=180);conn.set_tunnel(url.hostname,443)
 else:conn=http.client.HTTPSConnection(url.hostname,443,timeout=180)
 conn.putrequest('POST',url.path+'?'+url.query)
 for key,value in {**headers,'Content-Type':'application/zip' if file.suffix=='.zip' else 'text/plain','Content-Length':str(file.stat().st_size)}.items():conn.putheader(key,value)
 conn.endheaders();sent=0;next_report=32*1024**2
 with file.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):
   conn.send(block);sent+=len(block)
   if sent>=next_report:print(json.dumps({'file':file.name,'uploadedPercent':round(sent/file.stat().st_size*100)}),flush=True);next_report+=32*1024**2
 response=conn.getresponse();raw=response.read();conn.close()
 if response.status!=201:raise RuntimeError('Upload HTTP '+str(response.status))
 result=json.loads(raw)
 if result['size']!=file.stat().st_size or result.get('digest')!='sha256:'+sha:raise RuntimeError('GitHub digest mismatch')
 return result
main=release('v'+version);technical=release('updates-v'+version,True)
assets=[(main,folder/report['file'],report['sha256']),(main,folder/(report['file']+'.sha256'),None),(technical,folder/'update'/update['patch']['file'],update['patch']['sha256']),(technical,folder/'update'/(update['patch']['file']+'.sha256'),None)]
if a.action=='prepare':
 for rel,file,sha in assets:
  result=upload(rel,file,sha or digest(file));print(json.dumps({'uploaded':file.name,'digest':result.get('digest')}),flush=True)
 plan_file.write_text(json.dumps(plan,indent=2),encoding='utf-8')
elif a.action=='publish':
 for rel in (main,technical):
  existing=api('/releases/'+str(rel['id'])+'/assets')
  expected={file.name:sha or digest(file) for r,file,sha in assets if r['id']==rel['id']}
  if set(expected)!={item['name'] for item in existing}:raise RuntimeError('Unexpected extra release asset')
  if any(item.get('digest')!='sha256:'+expected[item['name']] for item in existing):raise RuntimeError('Remote asset verification failed')
 # Make technical resources available before the main installer becomes latest.
 api('/releases/'+str(technical['id']),'PATCH',{'tag_name':'updates-v'+version,'target_commitish':commit,'draft':False,'prerelease':True,'make_latest':'false'})
 main=api('/releases/'+str(main['id']),'PATCH',{'tag_name':'v'+version,'target_commitish':commit,'draft':False,'prerelease':False,'make_latest':'true'})
 print(json.dumps({'published':True,'url':main['html_url'],'assets':[item['name'] for item in api('/releases/'+str(main['id'])+'/assets')]}),flush=True)
else:print(json.dumps({'main':main['html_url'],'draft':main['draft'],'assets':[v['name'] for v in api('/releases/'+str(main['id'])+'/assets')]}))
