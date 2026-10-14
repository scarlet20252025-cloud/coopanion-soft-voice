"""Bounded loading trial; occupies only its own pageable memory and releases it on pressure."""
import argparse
import ctypes as C
import gc
import hashlib
import json
import os
import threading
import time
from pathlib import Path
import numpy as np
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.memory_metrics import snapshot

class Status(C.Structure):
    _fields_ = [('length', C.c_uint32), ('load', C.c_uint32)] + [
        (n, C.c_uint64) for n in ('total', 'available', 'pageTotal', 'pageAvailable',
                                 'virtualTotal', 'virtualAvailable', 'extended')]

def free():
    m = Status(); m.length = C.sizeof(m)
    if not C.windll.kernel32.GlobalMemoryStatusEx(C.byref(m)):
        raise C.WinError()
    return m.available / 1024**3

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--target-free', type=float, default=3.70)
    p.add_argument('--max-ballast-mib', type=int, default=2560)
    p.add_argument('--cycles', type=int, default=2)
    a = p.parse_args()
    if not 3.0 <= a.target_free <= 8 or not 0 <= a.max_ballast_mib <= 6144 or not 1 <= a.cycles <= 3:
        p.error('Target 3–8 GiB; ballast 0–6144 MiB; cycles 1–3')
    ballast = []
    report = {'initialFreeGiB': free(), 'targetFreeGiB': a.target_free,
              'maxBallastMiB': a.max_ballast_mib, 'cycles': [], 'safetyReleased': False}
    report['minFreeGiB'] = report['initialFreeGiB']
    stop = threading.Event()
    def watch():
        while not stop.wait(.05):
            f = free(); report['minFreeGiB'] = min(f, report['minFreeGiB'])
            if f < 1.5:
                report['safetyReleased'] = True
                ballast.clear(); gc.collect()
    t = threading.Thread(target=watch, daemon=True); t.start()
    model = None
    try:
        for cycle in range(a.cycles):
            ballast.clear(); gc.collect()
            row = {}
            report['cycles'].append(row)
            def prepare(stage, detail):
                if stage != 'check_memory': return
                # Apply pressure AFTER file validation, directly before the real
                # loading guard. Random pages avoid a misleading zero-page/compression test.
                while free() > a.target_free and len(ballast)*16 < a.max_ballast_mib and not report['safetyReleased']:
                    ballast.append(os.urandom(16*1024**2))
                if report['safetyReleased']:
                    raise RuntimeError('Safety threshold triggered; trial aborted')
                row.update(beforeLoadFreeGiB=free(), ballastMiB=len(ballast)*16)
                row['loadStarted'] = time.perf_counter()
            model = NativeEngine(a.runtime, on_stage=prepare)
            start = row.pop('loadStarted')
            row.update(loadMs=round((time.perf_counter()-start)*1000),
                       startupTimings=model.startup_timings, afterLoadFreeGiB=free(),
                       loadedMemory=snapshot(), samples=[])
            for text in ['我在这里陪你呀，慢慢来，不着急。',
                         '今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？']:
                chunks = []; start = time.perf_counter()
                model.synthesize_stream(text, 'trial', lambda a, r: chunks.append(a.copy()))
                pcm = np.concatenate(chunks)
                row['samples'].append({'sha256': hashlib.sha256(pcm.tobytes()).hexdigest(),
                                       'freeGiB': free(), 'memory': snapshot(),
                                       'synthesisMs': round((time.perf_counter()-start)*1000)})
                del chunks, pcm
                if report['safetyReleased']:
                    raise RuntimeError('Safety threshold triggered; trial aborted')
            model.close(); model = None; gc.collect()
            row['afterSleepFreeGiB'] = free()
    except Exception as e:
        report['error'] = str(e)
        raise
    finally:
        if model: model.close()
        stop.set(); t.join(); ballast.clear(); gc.collect()
        report['endFreeGiB'] = free()
        Path(a.output).write_text(json.dumps(report, indent=2), encoding='utf8')
        print(json.dumps(report))

if __name__ == '__main__':
    main()
