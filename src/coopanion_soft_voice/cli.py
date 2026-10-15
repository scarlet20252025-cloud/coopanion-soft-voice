import argparse,json,sys,time,traceback
from pathlib import Path
from .config import MODEL_REPO,MODEL_REVISION,profile,reference,validate_model

def doctor(runtime,mode='gpu'):
    if mode=='cache':
        from .cache_worker import doctor as cache_doctor
        return cache_doctor()
    if mode=='igpu':
        from .native_engine import settings
        config=settings(runtime)
        import sounddevice as sd
        sd.check_output_settings(samplerate=24000,channels=1,dtype='float32')
        return {'ok':True,'backend':'native-igpu','device':config['deviceName'],
                'voice':'soft-child-design-2','sampleRate':24000,'experimental':True}
    validate_model(runtime);reference()
    import torch
    if not torch.cuda.is_available():raise RuntimeError('NVIDIA CUDA GPU is required for this tested profile.')
    import sounddevice as sd
    from qwen_tts import Qwen3TTSModel
    sd.check_output_settings(samplerate=24000,channels=1,dtype='float32')
    return {'ok':True,'cuda':True,'device':torch.cuda.get_device_name(0),'torch':torch.__version__,
            'engine':'Qwen3-TTS 0.6B Base','voice':'soft-child-design-2','sampleRate':24000}

def load(runtime,mode='gpu',voice_pack=None,register_exit=True,on_stage=None,device_name=None):
    if mode=='igpu':
        from .native_engine import NativeEngine
        import atexit
        model=NativeEngine(runtime,voice_pack=voice_pack,on_stage=on_stage,device_name=device_name)
        # The verified native path builds graphs on the first real sentence.
        # Do not make the user wait for an extra discarded utterance on every wake.
        if register_exit:atexit.register(model.close)
        return model
    from .stream_engine import StreamEngine
    model=StreamEngine(profile(runtime))
    model.add_zero_shot_spk('',str(model.reference),'accepted')
    # Graph capture can affect the first output; discard and warm codec chunks too.
    model.synthesize_stream('准备好了。','accepted',lambda a,s:None)
    from .playback import speak
    return model

def worker(runtime,mode='gpu',voice_pack=None,device_name=None):
    if mode=='cache':
        from .cache_worker import worker as cache_worker
        return cache_worker()
    if mode == 'igpu':
        # NumPy only handles PCM here; NN inference uses GGML's own threads.
        # Avoid creating an unused BLAS worker stack for every logical CPU.
        import os
        os.environ['OPENBLAS_NUM_THREADS'] = '1'
    protocol=sys.stdout;sys.stdout=sys.stderr
    from .memory_metrics import snapshot
    def emit(obj):
        print('@@COSY@@'+json.dumps(obj,ensure_ascii=False),file=protocol,flush=True)
        # A bounded diagnostic sidecar contains status/numbers, never text or traces.
        from datetime import datetime,timezone
        fields=('type','stage','device','deviceType','engineVersion','processMemory','startupTimings','nativeSettings','errorKind','errorCode')
        safe={key:obj[key] for key in fields if key in obj}
        safe['atUtc']=datetime.now(timezone.utc).isoformat()
        try:
            folder=Path(runtime)/'cache';folder.mkdir(parents=True,exist_ok=True)
            temp=folder/'worker-status.json.tmp';temp.write_text(json.dumps(safe,ensure_ascii=False),encoding='utf-8');temp.replace(folder/'worker-status.json')
        except OSError:pass
    def stage(name,detail,**extra):emit(dict(type='status',stage=name,detail=detail,**extra))
    stage('load_model','加载语音模型')
    # Native initialization releases the GIL. Import the playback stack meanwhile,
    # and only announce ready after both are usable (previously this was hidden latency).
    from concurrent.futures import ThreadPoolExecutor
    from importlib import import_module
    with ThreadPoolExecutor(max_workers=1) as imports:
        playback_future=imports.submit(import_module, '.playback', __package__)
        try:model=load(runtime,mode,voice_pack,register_exit=False,on_stage=stage,device_name=device_name)
        except Exception as exc:
            guarded='GiB free RAM' in str(exc) and 'keeping text only' in str(exc)
            emit({'type':'error','stage':'initialization','errorKind':type(exc).__name__,
                  'errorCode':'memory_guard' if guarded else 'worker_error','error':str(exc)})
            raise
        stage('prepare_audio','正在检查播放器，完成后即可发声')
        try:speak=playback_future.result().speak
        except BaseException:model.close();raise
    from . import __version__
    def ready():emit({'type':'ready','engineVersion':__version__,'device':getattr(model,'device_name',mode),
        'deviceType':getattr(model,'device_type',None),'deviceVendorId':getattr(model,'vendor_id',None),'sampleRate':24000,'processMemory':snapshot(),
        'startupTimings':getattr(model,'startup_timings',None),'nativeSettings':getattr(model,'runtime_parameters',None)})
    ready()
    import math
    for line in sys.stdin:
        request_id=None
        try:
            msg=json.loads(line)
            if msg.get('type')=='quit':break
            if msg.get('type')=='sleep':
                parameters=getattr(model,'runtime_parameters',None)
                if model is not None:model.close();model=None
                import gc
                gc.collect()
                emit({'type':'slept','processMemory':snapshot(),'nativeSettings':parameters})
                continue
            if msg.get('type')=='wake':
                if model is None:model=load(runtime,mode,voice_pack,register_exit=False,on_stage=stage,device_name=device_name)
                ready()
                continue
            request_id=str(msg.get('id',''))
            if not request_id:raise ValueError('Missing request id')
            text=str(msg.get('text','')).strip()
            if not text:emit({'type':'done','id':request_id,'seconds':0});continue
            volume=float(msg.get('volume',65))
            if not math.isfinite(volume) or not 0<=volume<=100:raise ValueError('Invalid volume')
            supplied=msg.get('referenceAudio')
            if supplied and Path(supplied).resolve()!=reference():raise ValueError('Reference voice is locked')
            stage('synthesizing','正在生成固定参考声线')
            if model is None:model=load(runtime,mode,voice_pack,register_exit=False,device_name=device_name)
            if mode == 'igpu':
                enabled = msg.get('cacheRepeated', True)
                if type(enabled) is not bool: raise ValueError('Invalid repeated speech cache setting')
                model.cache_repeated = enabled
                if not enabled: model.pcm_cache.clear()
            result=speak(model,text,'accepted',volume,float(msg.get('speed',1)),request_id,stage,runtime,
                         playback_mode=msg.get('playbackMode','auto'))
            emit({**result,'processMemory':snapshot()})
        except Exception as exc:
            emit({'type':'error','id':request_id,'stage':'synthesizing','error':str(exc),'errorKind':type(exc).__name__,'trace':traceback.format_exc()})

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime',default='.runtime')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('download')
    sub.add_parser('devices')
    for name in ('doctor','worker'):
        part=sub.add_parser(name)
        part.add_argument('--mode',choices=['gpu','cache','igpu'],default='gpu')
        if name=='worker':
            part.add_argument('--voice-pack');part.add_argument('--device-name')
    sample=sub.add_parser('speak');sample.add_argument('text');sample.add_argument('--volume',type=float,default=65)
    render=sub.add_parser('render');render.add_argument('text');render.add_argument('--output',required=True)
    args=parser.parse_args(argv);runtime=Path(args.runtime).resolve()
    if args.command=='devices':
        from .native_engine import vulkan_devices
        print(json.dumps({'devices':vulkan_devices()},ensure_ascii=False));return
    if args.command=='download':
        from huggingface_hub import snapshot_download
        snapshot_download(MODEL_REPO,revision=MODEL_REVISION,local_dir=str(runtime/'clone-model'))
        validate_model(runtime,hashes=True);print('Model downloaded and verified.');return
    if args.command=='doctor':print(json.dumps(doctor(runtime,args.mode),ensure_ascii=False));return
    if args.command=='worker':worker(runtime,args.mode,args.voice_pack,args.device_name);return
    model=load(runtime)
    if args.command=='speak':
        if not 0<=args.volume<=100:raise ValueError('Volume must be between 0 and 100')
        from .playback import speak
        print(json.dumps(speak(model,args.text,'accepted',args.volume,1,'cli',lambda *a,**k:None,runtime),ensure_ascii=False))
    else:
        import numpy as np,soundfile as sf
        chunks=[];started=time.perf_counter();events=[]
        def receive(a,s):chunks.append(a.copy());events.append(time.perf_counter()-started)
        if len(args.text)>60:raise ValueError('Render test text must be at most 60 characters')
        model.synthesize_stream(args.text,'accepted',receive)
        sf.write(args.output,np.concatenate(chunks),24000,subtype='PCM_16')
        print(json.dumps({'firstChunkMs':round(events[0]*1000),'totalMs':round((time.perf_counter()-started)*1000),'output':args.output}))

if __name__=='__main__':main()
