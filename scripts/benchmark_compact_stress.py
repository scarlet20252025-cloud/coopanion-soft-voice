"""Bounded graph cache stress and light-sleep regression; no playback."""
import argparse,ctypes as C,gc,hashlib,json,time
from pathlib import Path
import numpy as np
from benchmark_reference_memory import memory
from coopanion_soft_voice.native_engine import NativeEngine
p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--output',required=True);a=p.parse_args()
r={'rows':[]};model=None
try:
 for cycle in range(2):
  start=time.perf_counter();model=NativeEngine(a.runtime);r.setdefault('loads',[]).append({'ms':round((time.perf_counter()-start)*1000),'memory':memory()})
  for i in range(6):
   chunks=[];start=time.perf_counter()
   text='我在这里陪你呀，慢慢来，不着急。' if i%2==0 else '今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？'
   model.synthesize_stream(text,'stress',lambda x,rate:chunks.append(x.copy()))
   pcm=np.concatenate(chunks);r['rows'].append({'cycle':cycle,'i':i,'seconds':round(time.perf_counter()-start,3),'sha256':hashlib.sha256(pcm.tobytes()).hexdigest(),'memory':memory()})
   del chunks,pcm
  model.close();model=None;gc.collect();r.setdefault('sleep',[]).append(memory())
finally:
 if model:model.close()
 Path(a.output).write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(r))
