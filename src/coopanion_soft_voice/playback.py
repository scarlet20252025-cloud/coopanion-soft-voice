import json,time
from pathlib import Path
from .pcm_player import PCMPlayer
from .speech_text import model_speech_pieces

def speak(model,text,key,volume,speed,request_id,stage,root):
    if speed!=1:raise ValueError('已确认童声使用原速 1.0')
    pieces=model_speech_pieces(model,text)
    started=time.perf_counter();first_ms=None
    piece_metrics=[]
    def playing():
        nonlocal first_ms
        first_ms=round((time.perf_counter()-started)*1000)
        stage('playing','流式连续播放',id=request_id,synthesisMs=first_ms)
    player=PCMPlayer(volume=volume/100,on_start=playing)
    def completed():player.producer_done=True
    try:
        for index,piece in enumerate(pieces):
            before=player.samples;piece_started=time.perf_counter()
            model.synthesize_stream(piece,key,player.push,on_complete=completed if index==len(pieces)-1 else None)
            piece_metrics.append({'characters':len(piece),'seconds':(player.samples-before)/model.sample_rate,
                                  'synthesisMs':round((time.perf_counter()-piece_started)*1000)})
        total=round((time.perf_counter()-started)*1000)
        if not player.samples:raise RuntimeError('模型没有返回声音')
        player.finish()
        result={'type':'done','id':request_id,'seconds':player.samples/model.sample_rate,
                'totalSynthesisMs':total,'firstChunkMs':first_ms,
                'firstDeviceCallbackMs':round((player.first_audio_at-started)*1000) if player.first_audio_at else None,
                'underrunMs':round(player.underrun_frames/player.rate*1000),
                'deviceUnderflows':player.device_underflows,'playbackMode':'continuous_pcm',
                'pieceCount':len(pieces),'pieces':piece_metrics}
        identity=getattr(model,'voice_conditioning',None)
        if isinstance(identity,dict):result['voiceConditioning']=identity
        mode=getattr(model,'buffer_mode',None)
        result['startupBufferMode']=mode if isinstance(mode,str) else 'backend-default'
        if mode in ('fixed','adaptive') and (player.underrun_frames or player.device_underflows):
            # A real device starvation event overrides optimistic cadence estimates.
            # Keep the conservative policy for the rest of this worker lifetime.
            model.buffer_mode='fixed'
        result['nextBufferMode']=getattr(model,'buffer_mode') if isinstance(mode,str) else 'backend-default'
        cache=Path(root)/'cache';cache.mkdir(parents=True,exist_ok=True)
        (cache/'last-stream-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except BaseException:
        player.abort();raise
