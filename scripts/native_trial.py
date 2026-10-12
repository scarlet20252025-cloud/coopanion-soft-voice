"""Isolated native benchmark: save samples, optionally test a muted output device."""
from coopanion_soft_voice.native_abi import *

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dll',required=True);p.add_argument('--dll-dir',action='append',default=[])
    p.add_argument('--model',required=True);p.add_argument('--codec',required=True)
    p.add_argument('--output',required=True);p.add_argument('--threads',type=int,choices=[2,4,8],default=4)
    p.add_argument('--silent-playback',action='store_true',help='Exercise actual output device at zero amplitude')
    p.add_argument('--max-tokens',type=int,default=240)
    p.add_argument('--texts-json',type=Path,help='UTF-8 JSON list of test strings')
    p.add_argument('--buffered',action='store_true',help='Compare whole-utterance codec batching against streaming')
    p.add_argument('--backend',choices=['CPU','BLAS','Vulkan0'],default='CPU')
    p.add_argument('--vulkan-visible',type=int,help='Required physical Vulkan device index for isolated iGPU experiment')
    args=p.parse_args()
    if args.backend=='Vulkan0':
        if args.vulkan_visible is None: p.error('Vulkan experiment requires explicit verified device index')
        os.environ['GGML_VK_VISIBLE_DEVICES']=str(args.vulkan_visible)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    os.environ['GGML_BACKEND']=args.backend;os.environ['QWEN_CPU_THREADS']=str(args.threads)
    dirs=[os.add_dll_directory(str(Path(d).resolve())) for d in [str(Path(args.dll).parent)]+args.dll_dir]
    kernel=C.windll.kernel32
    kernel.GetCurrentProcess.restype=C.c_void_p
    kernel.SetPriorityClass.argtypes=[C.c_void_p,C.c_ulong]
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):raise OSError('Cannot lower priority')
    import numpy as np
    import soundfile as sf
    from coopanion_soft_voice.config import reference,REFERENCE_TEXT,REFERENCE_SHA256
    dll=C.CDLL(str(Path(args.dll).resolve()))
    signatures={
        'qt_version':([],C.c_char_p),'qt_last_error':([],C.c_char_p),
        'qt_init_default_params':([C.POINTER(Init)],None),'qt_init':([C.POINTER(Init)],C.c_void_p),
        'qt_free':([C.c_void_p],None),'qt_tts_default_params':([C.POINTER(Params)],None),
        'qt_extract_voice_ref':([C.c_void_p,F32,C.c_int,C.POINTER(Voice)],C.c_int),
        'qt_voice_ref_free':([C.POINTER(Voice)],None),
        'qt_synthesize':([C.c_void_p,C.POINTER(Params),C.POINTER(Audio)],C.c_int),
        'qt_audio_free':([C.POINTER(Audio)],None)}
    for name,(argtypes,restype) in signatures.items():
        fn=getattr(dll,name);fn.argtypes=argtypes;fn.restype=restype
    init=Init();dll.qt_init_default_params(C.byref(init))
    if init.abi_version!=5:raise ValueError('Unsupported native ABI')
    init.talker_path=str(Path(args.model).resolve()).encode();init.codec_path=str(Path(args.codec).resolve()).encode()
    init.use_fa=False;init.max_batch=1
    started=time.perf_counter();ctx=dll.qt_init(C.byref(init))
    if not ctx:raise RuntimeError(dll.qt_last_error().decode())
    report={'engine':dll.qt_version().decode(),'threads':args.threads,'backend':args.backend,'streaming':not args.buffered,'max_tokens':args.max_tokens,'vulkan_visible':args.vulkan_visible,
            'reference_sha256':REFERENCE_SHA256,'load_seconds':time.perf_counter()-started,'runs':[]}
    voice=Voice()
    try:
        ref,rate=sf.read(reference(),dtype='float32');assert rate==24000 and ref.ndim==1
        started=time.perf_counter()
        code=dll.qt_extract_voice_ref(ctx,ref.ctypes.data_as(F32),len(ref),C.byref(voice))
        if code:raise RuntimeError(dll.qt_last_error().decode())
        report['reference_seconds']=time.perf_counter()-started
        print(json.dumps({'stage':'ready','load_seconds':report['load_seconds'],
                          'reference_seconds':report['reference_seconds']}),flush=True)
        texts=json.loads(args.texts_json.read_text(encoding='utf-8')) if args.texts_json else ['我会乖乖等你。','我们先学二十分钟，再一起休息一下吧。','今天的天气很好，我们慢慢来。']
        if not isinstance(texts,list) or not texts or any(not isinstance(t,str) or not t.strip() for t in texts):
            raise ValueError('Expected nonempty list of text strings')
        for i,text in enumerate(texts):
            params=Params();dll.qt_tts_default_params(C.byref(params))
            params.text=text.encode();params.lang=b'Chinese';params.ref_text=REFERENCE_TEXT.encode()
            params.ref_spk_emb=voice.ref_spk_emb;params.ref_spk_dim=voice.ref_spk_dim
            params.ref_codes=voice.ref_codes;params.ref_T=voice.ref_T
            params.seed=44;params.max_new_tokens=args.max_tokens
            params.temperature=.9;params.top_k=50;params.top_p=1;params.repetition_penalty=1.05
            params.subtalker_temperature=.9;params.subtalker_top_k=50;params.subtalker_top_p=1
            chunks=[];events=[];pending=[];started=time.perf_counter()
            player=None
            if args.silent_playback:
                from coopanion_soft_voice.pcm_player import PCMPlayer
                player=PCMPlayer(volume=0)
            @Cancel
            def timed_out(user):return time.perf_counter()-started>60
            params.cancel=timed_out
            callback_errors=[]
            def receive_impl(samples,n,user):
                chunk=np.ctypeslib.as_array(samples,shape=(n,)).copy()
                chunks.append(chunk)
                if player is not None:
                    if player.stream is not None:player.push(chunk,24000)
                    else:
                        pending.append(chunk)
                        if sum(len(a) for a in pending)>=28800:
                            player.push(np.concatenate(pending),24000);pending.clear()
                events.append({'at':time.perf_counter()-started,'seconds':n/24000})
                return time.perf_counter()-started<180
            @Chunk
            def receive(samples,n,user):
                try:return receive_impl(samples,n,user)
                except Exception as exc:
                    callback_errors.append(exc);return False
            if not args.buffered:params.on_chunk=receive
            audio=Audio()
            try:
                code=dll.qt_synthesize(ctx,C.byref(params),C.byref(audio))
            except BaseException:
                if player is not None:player.abort()
                raise
            if args.buffered and not code and audio.n_samples:
                receive(audio.samples,audio.n_samples,None)
            dll.qt_audio_free(C.byref(audio))
            if code or callback_errors:
                if player is not None:player.abort()
                raise RuntimeError(str(callback_errors[0]) if callback_errors else dll.qt_last_error().decode())
            elapsed=time.perf_counter()-started
            if not chunks:raise ValueError('No audio generated')
            result=np.concatenate(chunks)
            if not np.isfinite(result).all():raise ValueError('Nonfinite audio')
            path=out/f'native-{i+1}.wav';sf.write(path,result,24000,subtype='PCM_16')
            # Minimum initial buffer required for uninterrupted playback under this timing trace.
            before=0.;buffer_needed=0.
            for event in events:
                buffer_needed=max(buffer_needed,event['at']-before);before+=event['seconds']
            row={'text':text,'file':path.name,'first_chunk_seconds':events[0]['at'],
                 'generation_seconds':elapsed,'audio_seconds':len(result)/24000,
                 'rtf':elapsed/(len(result)/24000),'continuous_start_seconds':buffer_needed,
                 'clipping_fraction':float(np.mean(np.abs(result)>=.999)),
                 'events':events,'voice_approved':False}
            if player is not None:
                player.producer_done=True
                if pending:player.push(np.concatenate(pending),24000)
                try:player.finish()
                except BaseException:
                    player.abort();raise
                row['playback']={'volume':0,'prebuffer_audio_seconds':1.2,
                    'first_device_callback_seconds':player.first_audio_at-started if player.first_audio_at else None,
                    'underrun_seconds':player.underrun_frames/24000,'device_underflows':player.device_underflows}
            report['runs'].append(row)
            memory=Memory();memory.cb=C.sizeof(memory)
            get_memory=C.windll.psapi.GetProcessMemoryInfo
            get_memory.argtypes=[C.c_void_p,C.POINTER(Memory),C.c_ulong]
            if get_memory(kernel.GetCurrentProcess(),C.byref(memory),memory.cb):
                report['peak_working_set_mib']=memory.peakWorkingSet/2**20
                report['working_set_mib']=memory.workingSet/2**20
            (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in row.items() if k!='events'},ensure_ascii=False),flush=True)
    finally:
        dll.qt_voice_ref_free(C.byref(voice));dll.qt_free(ctx)
        for d in dirs:d.close()


if __name__=='__main__':main()
