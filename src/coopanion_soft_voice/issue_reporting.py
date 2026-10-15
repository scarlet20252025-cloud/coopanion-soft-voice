"""Create a redacted draft/fallback ZIP; --submit explicitly requests GitHub publication."""
import argparse,hashlib,json,os,subprocess,sys,urllib.request,zipfile
from pathlib import Path
try:
    from .diagnostics import redact,subset,METRICS,CONFIG,NATIVE_FIELDS,MEMORY_FIELDS,PERF
except ImportError:
    from collect_diagnostics import redact,subset,METRICS,CONFIG,NATIVE_FIELDS,MEMORY_FIELDS,PERF

REPO='scarlet20252025-cloud/coopanion-soft-voice'

def read_package(path):
    if Path(path).stat().st_size>5*1024*1024:raise ValueError('Diagnostic ZIP exceeds 5 MiB')
    with zipfile.ZipFile(path) as z:
        names=z.namelist();allowed={'REPORT.md','diagnostics.json','perf.log','AI_PROMPT.txt','manifest.json','issue-draft.md','analysis.md','submission.json'}
        if len(names)!=len(set(names)) or not set(names)<=allowed or sum(i.file_size for i in z.infolist())>8*1024*1024:raise ValueError('Unexpected diagnostic ZIP contents')
        meta=json.loads(z.read('manifest.json'));files={name:z.read(name) for name in names if name!='manifest.json'}
        if meta.get('schema')!=1 or set(meta['files'])!=set(files):raise ValueError('Diagnostic manifest mismatch')
        for name,data in files.items():
            if hashlib.sha256(data).hexdigest()!=meta['files'][name]:raise ValueError('Diagnostic checksum mismatch')
        report=json.loads(files['diagnostics.json'])
        if report.get('schema')!=1:raise ValueError('Unsupported diagnostic schema')
        return report,files

def credentials():
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:return token
    try:
        result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,timeout=10,env={**os.environ,'GCM_INTERACTIVE':'Never'},check=True)
        return dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line).get('password')
    except Exception:return None

def run(path,analysis=None,submit=False,issue_number=None,skip_duplicate=False):
    report,files=read_package(path)
    hardware=subset(report.get('hardware'),('os','version','build','cpu','logicalProcessors'))
    hardware['drivers']=[subset(d,('Name','DriverVersion')) for d in report.get('hardware',{}).get('drivers',[])[:10]]
    summary={**subset(report,('installedPythonPackageVersion','portableVersion','worldVersion','createdAtUtc')),
        'hardware':hardware,'runtime':subset(report.get('runtime'),('deviceName','deviceType','kvContext','compactGraphs','streamTextEmbedding','adaptiveKv','dllSha256','fixedVoiceProfile')),
        'preferences':subset(report.get('preferences'),CONFIG),'summary':subset(report.get('summary'),('realTimeFactor','underrunMs','deviceUnderflows','effectivePlaybackMode','matchingWorkers'))}
    samples=report.get('samples',[])
    if samples:
        summary['recentPlayback']=subset(samples[-1].get('recentPlayback'),METRICS)
        summary['nativeSettings']=subset(samples[-1].get('recentPlayback',{}).get('nativeSettings'),NATIVE_FIELDS)
        summary['processMemory']=subset(samples[-1].get('recentPlayback',{}).get('processMemory'),MEMORY_FIELDS)
        summary['voiceStage']=subset(samples[-1].get('voiceStage'),('type','stage','atUtc','engineVersion','device','deviceType','errorKind','errorCode'))
        summary['systemMemory']=subset(samples[-1].get('systemMemory'),('totalGiB','availableGiB','loadPercent'))
        summary['voiceProcesses']=[subset(row,(*MEMORY_FIELDS,'cpuPercentTotal')) for row in samples[-1].get('voiceProcesses',[])[:10]]
        summary['voiceGpuMemory']=[subset(row,('pid','source','scope','dedicatedMiB','sharedMiB')) for row in samples[-1].get('voiceGpuMemory',[])[:10]]
    raw_analysis=Path(analysis).read_text(encoding='utf-8') if analysis else '待 AI 填写复现、预期/实际、已确认原因和未验证假设。'
    # Path/token redaction is a backstop; the analysis author must also omit chat/PII.
    clean_analysis='\n'.join(redact(line) for line in raw_analysis.splitlines())[:16000]
    perf='\n'.join(redact(line) for line in files.get('perf.log',b'').decode('utf-8').splitlines() if PERF.match(line))[-10000:]
    actual_device=summary.get('recentPlayback',{}).get('deviceName') or summary['runtime'].get('deviceName')
    fingerprint=hashlib.sha256(json.dumps([summary.get('installedPythonPackageVersion'),summary.get('portableVersion'),actual_device,summary['summary'].get('effectivePlaybackMode'),clean_analysis.splitlines()[0] if clean_analysis else 'unknown'],ensure_ascii=False).encode()).hexdigest()[:16]
    title='[Bug] 语音诊断反馈：'+str(actual_device or '设备待核对')
    body='<!-- voice-diagnostic:'+fingerprint+' -->\n\n## 分析与复现\n\n'+clean_analysis+'\n\n## 脱敏诊断摘要\n\n```json\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n```\n\n## 相关性能日志\n\n```text\n'+(perf or '未收集到分阶段性能日志')+'\n```\n\n完整 ZIP 保存在用户本机，可从日志与诊断页导出。本摘要不包含原始聊天、账号配置、模型或音频。'
    result={'submitted':False,'repository':REPO,'reason':'未请求公开提交；已生成草稿'}
    if submit:
        token=credentials()
        if not token:result['reason']='GitHub 凭据不可用；已生成交回作者的 ZIP'
        else:
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Asryto-voice-diagnostics','Content-Type':'application/json'}
            api='https://api.github.com/repos/'+REPO
            def request(route,data=None):
                payload=json.dumps(data,ensure_ascii=False).encode('utf-8') if data is not None else None
                with urllib.request.urlopen(urllib.request.Request(api+route,data=payload,headers=headers),timeout=20) as response:return json.load(response)
            try:
                if issue_number is None:
                    issues=request('/issues?state=all&per_page=100')
                    matches=[i for i in issues if 'pull_request' not in i and 'voice-diagnostic:'+fingerprint in (i.get('body') or '')]
                    if matches:
                        issue_number=matches[0]['number']
                        if skip_duplicate:
                            result.update(submitted=True,url=matches[0]['html_url'],reason='已有关联 Issue；自动报告不重复发帖')
                item=None if result['submitted'] else request('/issues/'+str(issue_number)+'/comments',{'body':body}) if issue_number else request('/issues',{'title':title,'body':body})
                if item:result.update(submitted=True,url=item['html_url'],reason='已提交脱敏摘要与关键日志；完整 ZIP 保留供交回作者')
            except Exception as error:result['reason']='提交失败（'+type(error).__name__+'）；已生成交回作者的 ZIP'
    files.update({'issue-draft.md':body.encode('utf-8'),'analysis.md':clean_analysis.encode('utf-8'),'submission.json':json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')})
    destination=Path(path).with_name(Path(path).stem.removesuffix('-for-author')+'-for-author.zip')
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
        z.writestr('manifest.json',json.dumps({'schema':1,'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}},indent=2))
    print(json.dumps({**result,'archive':str(destination)},ensure_ascii=True));return result,destination

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--diagnostics',required=True);p.add_argument('--analysis');p.add_argument('--submit',action='store_true');p.add_argument('--issue-number',type=int)
    a=p.parse_args();run(a.diagnostics,a.analysis,a.submit,a.issue_number)
