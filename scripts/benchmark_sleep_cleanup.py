"""Check whether the documented CRT heap trim actually lowers committed memory."""
import ctypes as C,gc,json,time,argparse
from pathlib import Path
from benchmark_reference_memory import memory
from coopanion_soft_voice.native_engine import NativeEngine
p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--output',required=True);a=p.parse_args();rows=[]
for i in range(2):
 start=time.perf_counter();m=NativeEngine(a.runtime);load=round((time.perf_counter()-start)*1000)
 m.synthesize_stream('我在这里陪你呀，慢慢来，不着急。','sleep',lambda x,rate:None)
 m.close();del m;gc.collect();before=memory();start=time.perf_counter()
 trim=C.CDLL('ucrtbase.dll')._heapmin;trim.argtypes=[];trim.restype=C.c_int
 result=trim();elapsed=round((time.perf_counter()-start)*1000)
 rows.append({'loadMs':load,'before':before,'after':memory(),'heapminReturn':result,'trimMs':elapsed})
Path(a.output).write_text(json.dumps(rows,indent=2),encoding='utf-8');print(json.dumps(rows))
