"""Bounded low-memory loading trial. Releases its own ballast below 1 GiB free RAM."""
import argparse,ctypes as C,json,hashlib,threading,time,gc
from pathlib import Path
import numpy as np
from coopanion_soft_voice.native_engine import NativeEngine
class Status(C.Structure):
 _fields_=[('length',C.c_uint32),('load',C.c_uint32)]+[(n,C.c_uint64) for n in ('total','available','pageTotal','pageAvailable','virtualTotal','virtualAvailable','extended')]
def free():
 m=Status();m.length=C.sizeof(m);C.windll.kernel32.GlobalMemoryStatusEx(C.byref(m));return m.available/1024**3
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
ballast=[];report={'initialFreeGiB':free(),'cycles':[],'safetyReleased':False};stop=threading.Event()
while free()>3.70 and len(ballast)<40:ballast.append(bytearray(64*1024**2))
report['ballastMiB']=len(ballast)*64;report['minFreeGiB']=free()
def watch():
 while not stop.wait(.05):
  f=free();report['minFreeGiB']=min(f,report['minFreeGiB'])
  if f<1.0 and ballast:ballast.clear();report['safetyReleased']=True;gc.collect()
t=threading.Thread(target=watch,daemon=True);t.start();model=None
try:
 for cycle in range(2):
  row={'beforeLoadFreeGiB':free()};start=time.perf_counter();model=NativeEngine(args.runtime);row['loadMs']=round((time.perf_counter()-start)*1000);row['afterLoadFreeGiB']=free();row['samples']=[]
  for text in ['我在这里陪你呀，慢慢来，不着急。','今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？']:
   chunks=[];model.synthesize_stream(text,'trial',lambda a,r:chunks.append(a.copy()));pcm=np.concatenate(chunks);row['samples'].append({'sha256':hashlib.sha256(pcm.tobytes()).hexdigest(),'freeGiB':free()});del chunks,pcm
  model.close();model=None;gc.collect();row['afterSleepFreeGiB']=free();report['cycles'].append(row)
except Exception as e:report['error']=str(e)
finally:
 if model:model.close()
 stop.set();t.join();ballast.clear();gc.collect();report['endFreeGiB']=free()
 Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
