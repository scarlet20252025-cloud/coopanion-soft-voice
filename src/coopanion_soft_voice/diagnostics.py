"""Bounded, redacted diagnostics. No model inference, chat/config dump or telemetry."""
import argparse,base64,csv,ctypes as C,hashlib,importlib.metadata,json,math,os,re,shutil,subprocess,sys,time,zipfile
from datetime import datetime,timezone
from pathlib import Path

SCHEMA=1
REPO='https://github.com/scarlet20252025-cloud/coopanion-soft-voice'
PERF=re.compile(r'^\[Perf\] (PromptBuild|Prefill|TTFA|TalkerDecode|CodePredictor|HostCompose|CodecDecode|Total)\b')
METRICS=('atUtc','seconds','totalSynthesisMs','realTimeFactor','firstChunkMs','firstDeviceCallbackMs','underrunMs','deviceUnderflows','pieceCount','startupBufferMode','requestedPlaybackMode','effectivePlaybackMode','smoothPlayback','engineVersion','deviceName','deviceType','cachedPieces','generatedPieces','audioSource')
CONFIG=('volume','maxQueue','maxAgeSec','pollMs','lowPowerMode','idleUnloadSec','keepWorker','lowMemoryMiB','autoRecover','syncBubbles','playbackMode','deviceName','cacheRepeated')
MEMORY_FIELDS=('pid','privateMiB','residentMiB','peakResidentMiB')
NATIVE_FIELDS=('memoryPolicy','disableHostVisibleVram','cpuThreads','kvContext','compactGraphs','streamTextEmbedding','maxNodesPerSubmit','adaptiveKv','kvPrecision','kvCapacity','kvAllocatedMiB','minimumFreeGiB','pcmCacheBytes','pcmCacheMaximumBytes','pcmCacheHits','pcmCacheMisses','pcmCacheEntries')
STARTUP_FIELDS=('validationMs','modelInitMs','totalMs','availableBeforeLoadGiB')

def subset(value,fields):
    return {key:clean(value[key]) for key in fields if key in value} if isinstance(value,dict) else {}

def redact(value):
    text=str(value)
    # A quoted path can contain spaces. Mask it before the bare-path fallback.
    text=re.sub(r'(?i)([\"\'])(?:[a-z]:[\\/]|\\\\).*?\1','[path]',text)
    text=re.sub(r'(?i)(?:[a-z]:[\\/]|\\\\)[^\r\n<>;,]*','[path]',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[email]',text)
    text=re.sub(r'(?i)\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{8,}','[secret]',text)
    text=re.sub(r'(?i)\bbearer\s+[^\s,;]+','Bearer [redacted]',text)
    text=re.sub(r'(?im)\b(authorization|api[_-]?key|access[_-]?token|cookie|password)\s*[:= ]\s*[^\r\n]+',r'\1=[redacted]',text)
    return text[:1000]

def clean(value):
    if isinstance(value,str):return redact(value)
    if value is None or isinstance(value,(bool,int)):return value
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,list):return [clean(v) for v in value[:150]]
    if isinstance(value,dict):return {redact(k):clean(v) for k,v in list(value.items())[:100]}
    return None

def read_json(path):
    try:
        if Path(path).stat().st_size>1024*1024:return {}
        value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def ps_json(script):
    code='[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);'+script
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(code.encode('utf-16le')).decode()],capture_output=True,timeout=12,check=True)
    return json.loads(result.stdout.decode('utf-8-sig'))

def static_info():
    if sys.platform!='win32':return {'platform':sys.platform,'logicalProcessors':os.cpu_count(),'note':'Windows hardware counters unavailable'}
    try:
        data=ps_json("$o=Get-CimInstance Win32_OperatingSystem;$c=Get-CimInstance Win32_Processor;[pscustomobject]@{os=$o.Caption;version=$o.Version;build=$o.BuildNumber;cpu=($c.Name -join ', ');logicalProcessors=($c|Measure-Object NumberOfLogicalProcessors -Sum).Sum;drivers=@(Get-CimInstance Win32_VideoController|Select-Object Name,DriverVersion)}|ConvertTo-Json -Depth 4 -Compress")
        return clean(data)
    except Exception as error:return {'platform':sys.platform,'logicalProcessors':os.cpu_count(),'warning':type(error).__name__}

def vulkan_info():
    if sys.platform!='win32':return []
    class Create(C.Structure):
        _fields_=[('sType',C.c_uint32),('next',C.c_void_p),('flags',C.c_uint32),('app',C.c_void_p),('nl',C.c_uint32),('layers',C.c_void_p),('ne',C.c_uint32),('extensions',C.c_void_p)]
    v=C.WinDLL('vulkan-1.dll');instance=C.c_void_p();create=Create();create.sType=1
    v.vkCreateInstance.argtypes=[C.POINTER(Create),C.c_void_p,C.POINTER(C.c_void_p)]
    v.vkEnumeratePhysicalDevices.argtypes=[C.c_void_p,C.POINTER(C.c_uint32),C.c_void_p]
    v.vkGetPhysicalDeviceProperties.argtypes=[C.c_void_p,C.c_void_p]
    v.vkGetPhysicalDeviceProperties.restype=None
    v.vkGetPhysicalDeviceMemoryProperties.argtypes=[C.c_void_p,C.c_void_p]
    v.vkGetPhysicalDeviceMemoryProperties.restype=None
    v.vkDestroyInstance.argtypes=[C.c_void_p,C.c_void_p]
    v.vkDestroyInstance.restype=None
    if v.vkCreateInstance(C.byref(create),None,C.byref(instance)):raise RuntimeError('Vulkan instance unavailable')
    try:
        count=C.c_uint32();v.vkEnumeratePhysicalDevices(instance,C.byref(count),None)
        if count.value>64:raise RuntimeError('Unexpected Vulkan device count')
        devices=(C.c_void_p*count.value)();v.vkEnumeratePhysicalDevices(instance,C.byref(count),devices);out=[]
        for index,device in enumerate(devices):
            props=C.create_string_buffer(4096);v.vkGetPhysicalDeviceProperties(device,props)
            kind=int.from_bytes(props.raw[16:20],'little')
            if kind not in (1,2):continue
            memory=C.create_string_buffer(1024);v.vkGetPhysicalDeviceMemoryProperties(device,memory)
            ntypes=min(32,int.from_bytes(memory.raw[:4],'little'));nheaps=min(16,int.from_bytes(memory.raw[260:264],'little'))
            heaps=[{'sizeGiB':round(int.from_bytes(memory.raw[264+i*16:272+i*16],'little')/1024**3,3),'deviceLocal':bool(int.from_bytes(memory.raw[272+i*16:276+i*16],'little')&1)} for i in range(nheaps)]
            types=[{'flags':int.from_bytes(memory.raw[4+i*8:8+i*8],'little'),'heap':int.from_bytes(memory.raw[8+i*8:12+i*8],'little')} for i in range(ntypes)]
            out.append({'index':index,'name':redact(props.raw[20:276].split(b'\0')[0].decode('utf-8')),'kind':'integrated' if kind==1 else 'discrete','vendorId':int.from_bytes(props.raw[8:12],'little'),'memoryHeaps':heaps,'memoryTypes':types})
        return out
    finally:v.vkDestroyInstance(instance,None)

def system_memory():
    if sys.platform!='win32':return None
    class Status(C.Structure):
        _fields_=[('length',C.c_uint32),('load',C.c_uint32)]+[(n,C.c_uint64) for n in ('total','available','pageTotal','pageAvailable','virtualTotal','virtualAvailable','extended')]
    status=Status();status.length=C.sizeof(status)
    if not C.windll.kernel32.GlobalMemoryStatusEx(C.byref(status)):return None
    return {'totalGiB':round(status.total/1024**3,3),'availableGiB':round(status.available/1024**3,3),'loadPercent':status.load}

def owned_workers(runtime):
    if sys.platform!='win32':return []
    try:rows=ps_json("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\"|Select-Object ProcessId,CommandLine)|ConvertTo-Json -Compress") or []
    except Exception:return []
    if isinstance(rows,dict):rows=[rows]
    expected=str(Path(runtime).resolve()).lower();out=[]
    for row in rows:
        cmd=row.get('CommandLine') or ''
        if 'coopanion_soft_voice.cli' not in cmd or not re.search(r'\bworker\b',cmd):continue
        found=re.search(r'--runtime\s+(?:\"([^\"]+)\"|(\S+))',cmd)
        if found and str(Path(found.group(1) or found.group(2)).resolve()).lower()==expected:out.append(int(row['ProcessId']))
    return out

def process_memory(pid):
    if sys.platform!='win32':return None
    class Counters(C.Structure):
        _fields_=[('cb',C.c_ulong),('faults',C.c_ulong)]+[(n,C.c_size_t) for n in ('peakWorkingSet','workingSet','peakPaged','paged','peakNonpaged','nonpaged','pagefile','peakPagefile','privateUsage')]
    k=C.windll.kernel32;k.OpenProcess.restype=C.c_void_p;k.OpenProcess.argtypes=[C.c_ulong,C.c_bool,C.c_ulong];k.CloseHandle.argtypes=[C.c_void_p]
    handle=k.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        api=C.windll.psapi.GetProcessMemoryInfo;api.argtypes=[C.c_void_p,C.POINTER(Counters),C.c_ulong]
        counter=Counters();counter.cb=C.sizeof(counter)
        if not api(handle,C.byref(counter),counter.cb):return None
        out={'pid':pid,'privateMiB':round(counter.privateUsage/1024**2,1),'residentMiB':round(counter.workingSet/1024**2,1),'peakResidentMiB':round(counter.peakWorkingSet/1024**2,1)}
        values=[C.c_uint64() for _ in range(4)]
        k.GetProcessTimes.argtypes=[C.c_void_p,*([C.POINTER(C.c_uint64)]*4)]
        if k.GetProcessTimes(handle,*[C.byref(v) for v in values]):out['cpuSeconds']=(values[2].value+values[3].value)/1e7
        return out
    finally:k.CloseHandle(handle)

def nvidia_sample():
    exe=shutil.which('nvidia-smi')
    if not exe:return []
    fields=['name','driver_version','pstate','clocks.current.graphics','clocks.current.memory','power.draw','utilization.gpu','memory.used','memory.total']
    try:
        result=subprocess.run([exe,'--query-gpu='+','.join(fields),'--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,check=True)
        return [dict(zip(fields,[redact(value.strip()) for value in row])) for row in csv.reader(result.stdout.splitlines())]
    except Exception:return []


def process_gpu_memory(pids):
    try:
        try:from .gpu_memory import GpuMemory
        except ImportError:from gpu_memory import GpuMemory
        out=[]
        for pid in pids:
            with GpuMemory(pid) as gpu:out.append({'pid':pid,**gpu.snapshot()})
        return out
    except (ImportError,OSError):return []

def selected_metrics(value):
    out={key:clean(value[key]) for key in METRICS if key in value}
    for key,fields in [('processMemory',MEMORY_FIELDS),('nativeSettings',NATIVE_FIELDS)]:
        if isinstance(value.get(key),dict):out[key]=subset(value[key],fields)
    pieces=value.get('pieces',[])
    out['pieces']=[subset(p,('characters','seconds','synthesisMs','cacheHit')) for p in pieces[:30] if isinstance(p,dict)] if isinstance(pieces,list) else []
    return out

def perf_tail(file):
    try:
        with Path(file).open('rb') as stream:
            stream.seek(max(0,Path(file).stat().st_size-128*1024));lines=stream.read().decode('utf-8',errors='replace').splitlines()
        # Reconstruct numeric performance rows instead of copying arbitrary log text.
        rows=[]
        for line in lines:
            match=PERF.match(line)
            if match:
                tail=line[match.end():]
                duration=re.match(r'\s+(\d+(?:\.\d+)?)\s+ms\b',tail)
                if not duration:continue
                fields=[duration.group(1)+' ms']
                for label,pattern in (
                    ('frames',r'\((\d+) frames'),('ms/frame',r'(\d+(?:\.\d+)?) ms/frame'),
                    ('audioSeconds',r'audio (\d+(?:\.\d+)?) s'),('RTF',r'RTF (\d+(?:\.\d+)?)')):
                    value=re.search(pattern,tail)
                    if value:fields.append(label+'='+value.group(1))
                rows.append('[Perf] '+match.group(1)+' | '+' | '.join(fields))
        return '\n'.join(rows)[-48*1024:]
    except OSError:return ''

def collect(runtime,output,data_dir=None,seconds=0,interval=2,log_file=None,world_version=None):
    if type(seconds) is not int or type(interval) is not int or not 0<=seconds<=300 or not 1<=interval<=30:raise ValueError('Monitor duration must be 0–300 seconds; interval 1–30 seconds')
    if world_version is not None and not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',world_version):raise ValueError('Invalid World version')
    root=Path(runtime).resolve();output=Path(output).resolve()
    if not root.is_dir():raise ValueError('--runtime must be a directory')
    if output.exists() and not output.is_dir():raise ValueError('--output must be a directory')
    data=Path(data_dir).resolve() if data_dir else None
    hardware=static_info();warnings=[]
    try:hardware['vulkanDevices']=vulkan_info()
    except Exception as error:warnings.append('Vulkan inventory unavailable: '+type(error).__name__)
    marker=read_json(root/'portable-manifest.json');cfg=read_json(root/'native-runtime.json') or marker.get('runtime',{})
    preferences=read_json(data/'settings.json') if data else {}
    try:package_version=importlib.metadata.version('coopanion-soft-voice')
    except importlib.metadata.PackageNotFoundError:package_version='unknown'
    samples=[];pids=owned_workers(root);started=time.monotonic();previous={};previous_at=None
    while True:
        metrics=read_json(root/'cache/last-stream-metrics.json');status=read_json(root/'cache/worker-status.json')
        now=time.monotonic();processes=[m for pid in pids if (m:=process_memory(pid)) is not None]
        for m in processes:
            if previous_at is not None and m['pid'] in previous and 'cpuSeconds' in m:
                m['cpuPercentTotal']=round(max(0,m['cpuSeconds']-previous[m['pid']])/(now-previous_at)/max(1,os.cpu_count() or 1)*100,2)
        previous={m['pid']:m['cpuSeconds'] for m in processes if 'cpuSeconds' in m};previous_at=now
        stage=subset(status,('type','stage','atUtc','engineVersion','device','deviceType','errorKind','errorCode'))
        for key,fields in [('processMemory',MEMORY_FIELDS),('startupTimings',STARTUP_FIELDS),('nativeSettings',NATIVE_FIELDS)]:
            if key in status:stage[key]=subset(status[key],fields)
        samples.append({'atUtc':datetime.now(timezone.utc).isoformat(),'systemMemory':system_memory(),
            'voiceProcesses':processes,'voiceGpuMemory':process_gpu_memory(pids),
            'gpuSystemWide':nvidia_sample(),'voiceStage':stage,
            'recentPlayback':selected_metrics(metrics)})
        elapsed=time.monotonic()-started
        print(f'Diagnostics: {min(seconds,round(elapsed))}/{seconds}s, {len(processes)} matching voice worker(s)',file=sys.stderr,flush=True)
        if elapsed>=seconds:break
        time.sleep(min(interval,max(0,seconds-elapsed)))
        pids=owned_workers(root)
    native={k:clean(cfg[k]) for k in ('deviceName','deviceType','deviceSelectedExplicitly','kvContext','compactGraphs','streamTextEmbedding','adaptiveKv','dllSha256') if k in cfg}
    report={'schema':SCHEMA,'createdAtUtc':datetime.now(timezone.utc).isoformat(),'author':'Asryto','repository':REPO,
        'collectorVersion':'1.1','installedPythonPackageVersion':package_version,'portableVersion':marker.get('version'),'worldVersion':world_version or marker.get('worldVersion'),
        'hardware':hardware,'runtime':native,'preferences':{k:clean(preferences.get('config',{}).get(k)) for k in CONFIG if k in preferences.get('config',{})},
        'samples':samples,'warnings':warnings,'limitations':['GPU samples cover all applications, not only TTS.','Private process memory is not total VRAM.','Matching process count may include a Windows venv launcher; it is not a count of loaded models.','Recent playback may be historical or offline; compare timestamps and matching worker presence.','No chat, account config, environment dump, raw command lines, model weights or audio is collected.']}
    model=cfg.get('speechOnly',{});report['runtime']['fixedVoiceProfile']=model.get('format')==1
    last=samples[-1]['recentPlayback'];rtf=last.get('realTimeFactor')
    if rtf is None and last.get('seconds',0)>0:rtf=round(last.get('totalSynthesisMs',0)/1000/last['seconds'],3)
    report['summary']={'realTimeFactor':rtf,'underrunMs':last.get('underrunMs'),'deviceUnderflows':last.get('deviceUnderflows'),'effectivePlaybackMode':last.get('effectivePlaybackMode'),'matchingWorkers':len(samples[-1]['voiceProcesses'])}
    markdown='# 轻量化本地语音引擎诊断报告\n\n作者 Asryto · '+report['createdAtUtc']+'\n\n仓库：'+REPO+'\n\n'
    labels={'realTimeFactor':'合成耗时 / 音频时长（小于 1 表示快于实时）','underrunMs':'播放断流（毫秒）','deviceUnderflows':'设备欠载（次数）','effectivePlaybackMode':'实际播放策略','matchingWorkers':'匹配到的语音进程数'}
    markdown+='## 关键读数\n\n'+ '\n'.join('- '+labels[k]+': '+str(v if v is not None else '未测') for k,v in report['summary'].items())+'\n\n'
    stage=samples[-1]['voiceStage']
    markdown+='## 故障与采集范围\n\n- 当前阶段：'+str(stage.get('stage',stage.get('type','未知')))+'\n- 错误类型：'+str(stage.get('errorKind','未记录'))+'\n- 监测时长 / 样本数：'+str(seconds)+' 秒 / '+str(len(samples))+'\n- 采集不加载模型、不额外合成；近期播放时间见 diagnostics.json。\n\n'

    markdown+='## 分析要求\n\n先区分合成吞吐、首次出声、播放欠载与加载耗时；RTF>1 不能靠固定小缓冲保证连续。比较真实设备、驱动、显存分配和阶段耗时；冷/暖启动、背景 GPU 负载与测试代码版本要分别记录。不要把 GPU 系统总占用当成 TTS 占用，也不要把历史 JSON 当作当前会话。\n\n'
    markdown+='## 提交或交回作者\n\n按照 docs/AI_BUG_REPORTS.md 去重并提交 Issue，附 diagnostics.json 和 perf.log 的必要脱敏内容。当前用户未授权公开报障或 GitHub 无法提交时，保留这个 ZIP 和分析稿交回用户，不假装已提交。\n'
    prompt='仓库 '+REPO+'。请分析随附诊断包，结合复现现象核对性能与错误。当前用户已授权向该仓库公开报障时，先查重，再提交脱敏 Issue 和必要诊断日志；未获授权或不能自主提交时，把诊断、分析和 Issue 草稿打包交回用户。不要上传聊天、密钥、完整配置、原始路径或音频。\n'
    log=perf_tail(log_file or (data/'worker.log' if data else root/'worker.log'))
    payloads={'REPORT.md':markdown.encode('utf-8'),'diagnostics.json':json.dumps(clean(report),ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'),'perf.log':log.encode('utf-8'),'AI_PROMPT.txt':prompt.encode('utf-8')}
    manifest={'schema':SCHEMA,'files':{name:hashlib.sha256(content).hexdigest() for name,content in payloads.items()}}
    payloads['manifest.json']=json.dumps(manifest,indent=2).encode('utf-8')
    output.mkdir(parents=True,exist_ok=True);archive=output/('voice-diagnostics-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,content in payloads.items():z.writestr(name,content)
    print(json.dumps({'ok':True,'archive':str(archive),'bytes':archive.stat().st_size,'samples':len(samples),'uploadPerformed':False},ensure_ascii=True))
    return archive

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True);p.add_argument('--output',required=True);p.add_argument('--data-dir');p.add_argument('--seconds',type=int,default=0);p.add_argument('--interval',type=int,default=2);p.add_argument('--log-file')
    a=p.parse_args();collect(a.runtime,a.output,a.data_dir,a.seconds,a.interval,a.log_file)

if __name__=='__main__':main()
