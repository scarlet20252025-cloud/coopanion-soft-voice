import json,time
from pathlib import Path
from .pcm_player import PCMPlayer
from .speech_text import model_speech_pieces

def speak(model,text,key,volume,speed,request_id,stage,root,playback_mode='auto'):
    if speed!=1:raise ValueError('已确认童声使用原速 1.0')
    if playback_mode not in ('auto','stream','buffered'):raise ValueError('Unknown playback mode')
    pieces=model_speech_pieces(model,text)
    cache=Path(root)/'cache';policy_file=cache/'playback-policy.json'
    device=getattr(model,'device_name',None);identity=getattr(model,'voice_conditioning',{})
    signature=identity.get('conditioningSha256') if isinstance(identity,dict) else None
    if isinstance(device,str) and isinstance(signature,str):
        try:
            saved=json.loads(policy_file.read_text(encoding='utf-8'))
            if saved.get('device')==device and saved.get('conditioning')==signature and saved.get('buffered') is True:model.prefer_buffered=True
        except (OSError,ValueError,AttributeError):pass
    started=time.perf_counter();first_ms=None
    piece_metrics=[];effective='stream' if playback_mode=='stream' else 'buffered' if playback_mode=='buffered' else None
    if playback_mode=='auto' and getattr(model,'prefer_buffered',False):effective='buffered'
    def playing():
        nonlocal first_ms
        first_ms=round((time.perf_counter()-started)*1000)
        stage('playing','整句连续播放' if effective=='buffered' else '流式连续播放',id=request_id,synthesisMs=first_ms)
    player=PCMPlayer(volume=volume/100,on_start=playing,defer_start=playback_mode!='stream')
    def receive(audio,rate):
        nonlocal effective
        # Inspect production cadence BEFORE the first playable sample; exclude prefill.
        # A fixed buffer cannot sustain a producer that is slower than playback.
        if effective is None:
            cadence=getattr(model,'last_start_buffer',None) or {}
            rtf=cadence.get('productionRtf')
            effective='stream' if isinstance(rtf,(float,int)) and 0<=rtf<.8 else 'buffered'
            if effective=='stream':player.start_playback()
            else:stage('buffering','正在生成完整语音，完成后连续播放；此设备优先避免断续。',id=request_id)
        player.push(audio,rate)
    def completed():player.producer_done=True
    try:
        for index,piece in enumerate(pieces):
            before=player.samples;piece_started=time.perf_counter()
            model.synthesize_stream(piece,key,receive,on_complete=completed if index==len(pieces)-1 else None)
            piece_metrics.append({'characters':len(piece),'seconds':(player.samples-before)/model.sample_rate,
                                  'synthesisMs':round((time.perf_counter()-piece_started)*1000)})
        total=round((time.perf_counter()-started)*1000)
        if not player.samples:raise RuntimeError('模型没有返回声音')
        player.finish()
        seconds=player.samples/model.sample_rate
        result={'type':'done','id':request_id,'seconds':seconds,
                'totalSynthesisMs':total,'realTimeFactor':round(total/1000/seconds,3),'firstChunkMs':first_ms,
                'firstDeviceCallbackMs':round((player.first_audio_at-started)*1000) if player.first_audio_at else None,
                'underrunMs':round(player.underrun_frames/player.rate*1000),
                'deviceUnderflows':player.device_underflows,'playbackMode':'continuous_pcm',
                'requestedPlaybackMode':playback_mode,'effectivePlaybackMode':effective,
                'smoothPlayback':not (player.underrun_frames or player.device_underflows),
                'pieceCount':len(pieces),'pieces':piece_metrics}
        identity=getattr(model,'voice_conditioning',None)
        if isinstance(identity,dict):result['voiceConditioning']=identity
        if isinstance(device,str):result.update(deviceName=device,deviceType=getattr(model,'device_type',None))
        parameters=getattr(model,'runtime_parameters',None)
        if isinstance(parameters,dict):result['nativeSettings']=parameters
        from . import __version__
        from .memory_metrics import snapshot
        from datetime import datetime,timezone
        result.update(engineVersion=__version__,processMemory=snapshot(),atUtc=datetime.now(timezone.utc).isoformat())
        if not result['smoothPlayback']:model.prefer_buffered=True
        elif playback_mode=='stream' and result['realTimeFactor']<.8:model.prefer_buffered=False
        if isinstance(device,str) and isinstance(signature,str):
            cache.mkdir(parents=True,exist_ok=True)
            policy_file.write_text(json.dumps({'device':device,'conditioning':signature,'buffered':bool(getattr(model,'prefer_buffered',False))}),encoding='utf-8')
        mode=getattr(model,'buffer_mode',None)
        result['startupBufferMode']=mode if isinstance(mode,str) else 'backend-default'
        if mode in ('fixed','adaptive') and not result['smoothPlayback']:
            # A real device starvation event overrides optimistic cadence estimates.
            # Keep the conservative policy for the rest of this worker lifetime.
            model.buffer_mode='fixed'
        result['nextBufferMode']=getattr(model,'buffer_mode',None) if isinstance(mode,str) else 'backend-default'
        cache.mkdir(parents=True,exist_ok=True)
        (cache/'last-stream-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except BaseException:
        player.abort();raise
