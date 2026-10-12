import json,re,time
from pathlib import Path
from .pcm_player import PCMPlayer

def speak(model,text,key,volume,speed,request_id,stage,root):
    if speed!=1:raise ValueError('已确认童声使用原速 1.0')
    pieces=[];current=''
    for sentence in re.split(r'(?<=[。！？!?；;])',text):
        if len(current)+len(sentence)>60 and current:
            pieces.append(current);current=''
        while len(sentence)>60:
            pieces.append(sentence[:60]);sentence=sentence[60:]
        current+=sentence
    if current:pieces.append(current)
    pieces=[piece for piece in pieces if piece.strip()]
    started=time.perf_counter();first_ms=None
    def playing():
        nonlocal first_ms
        first_ms=round((time.perf_counter()-started)*1000)
        stage('playing','流式连续播放',id=request_id,synthesisMs=first_ms)
    player=PCMPlayer(volume=volume/100,on_start=playing)
    def completed():player.producer_done=True
    try:
        for index,piece in enumerate(pieces):
            model.synthesize_stream(piece,key,player.push,on_complete=completed if index==len(pieces)-1 else None)
        total=round((time.perf_counter()-started)*1000)
        if not player.samples:raise RuntimeError('模型没有返回声音')
        player.finish()
        result={'type':'done','id':request_id,'seconds':player.samples/model.sample_rate,
                'totalSynthesisMs':total,'firstChunkMs':first_ms,
                'firstDeviceCallbackMs':round((player.first_audio_at-started)*1000) if player.first_audio_at else None,
                'underrunMs':round(player.underrun_frames/player.rate*1000),
                'deviceUnderflows':player.device_underflows,'playbackMode':'continuous_pcm'}
        cache=Path(root)/'cache';cache.mkdir(parents=True,exist_ok=True)
        (cache/'last-stream-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    except BaseException:
        player.abort();raise
