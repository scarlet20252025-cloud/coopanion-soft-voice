"""Compare startup policies on one engine; plays four short/long samples."""
import argparse
import json
import hashlib
import numpy as np
from pathlib import Path
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.playback import speak

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime',required=True);p.add_argument('--output',required=True)
a=p.parse_args(); model=NativeEngine(a.runtime)
rows=[]; references={}
try:
    for mode,text in [
        ('fixed','我在这里陪你呀，慢慢来，不着急。'),
        ('adaptive','我在这里陪你呀，慢慢来，不着急。'),
        ('fixed','今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？'),
        ('adaptive','今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？')]:
        model.buffer_mode=mode
        chunks=[]; original=model.synthesize_stream
        def traced(text,key,receive,on_complete=None):
            def output(audio,rate): chunks.append(audio.copy());receive(audio,rate)
            return original(text,key,output,on_complete)
        model.synthesize_stream=traced
        row=speak(model,text,'accepted',65,1,'bench-'+str(len(rows)),lambda *args,**kwargs:None,Path(a.runtime))
        model.synthesize_stream=original
        pcm=np.concatenate(chunks)
        row['pcmSha256']=hashlib.sha256(pcm.tobytes()).hexdigest()
        if mode=='fixed':references[text]=pcm
        elif len(pcm)==len(references[text]):
            row['maxAbsoluteDifference']=float(np.max(np.abs(pcm-references[text])))
        row['policy']=mode; row['buffer']=model.last_start_buffer;rows.append(row)
finally:
    model.close();Path(a.output).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rows,ensure_ascii=False))
