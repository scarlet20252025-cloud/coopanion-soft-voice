"""Run each variant in a fresh process. No playback, no running-app changes."""
import argparse
import ctypes as C
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.native_abi import Memory


def memory():
    kernel = C.windll.kernel32
    kernel.GetCurrentProcess.restype = C.c_void_p
    api = C.windll.psapi.GetProcessMemoryInfo
    api.argtypes = [C.c_void_p, C.POINTER(Memory), C.c_ulong]
    m = Memory(); m.cb = C.sizeof(m)
    if not api(kernel.GetCurrentProcess(), C.byref(m), m.cb):
        raise C.WinError()
    return dict(privateCommitMiB=round(m.pagefile/1024**2, 1),
                workingSetMiB=round(m.workingSet/1024**2, 1),
                peakWorkingSetMiB=round(m.peakWorkingSet/1024**2, 1))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True)
    p.add_argument('--variant', choices=['baseline', 'cached'], required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--texts', help='JSON array of 1–60 character strings for a broader regression corpus')
    p.add_argument('--no-prewarm', action='store_true', help='Measure the first real sentence without a discarded warmup')
    p.add_argument('--buffer-mode', choices=['fixed','adaptive'], default='adaptive')
    args = p.parse_args()
    texts = json.loads(Path(args.texts).read_text(encoding='utf-8')) if args.texts else [
        '我在这里陪你呀，慢慢来，不着急。',
        '今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？',
        '我在这里陪你呀，慢慢来，不着急。']
    if not isinstance(texts, list) or not texts or any(not isinstance(t,str) or not t.strip() or len(t)>60 for t in texts):
        p.error('texts must be a nonempty array of 1–60 character strings')
    started = time.perf_counter()
    model = NativeEngine(args.runtime, use_reference_cache=args.variant == 'cached', buffer_mode=args.buffer_mode)
    report = dict(variant=args.variant, cacheHit=model.reference_cache_hit,
                  loadSeconds=round(time.perf_counter()-started, 3), loaded=memory())
    report['startupTimings'] = model.startup_timings
    report['prewarm'] = not args.no_prewarm
    report['bufferMode'] = args.buffer_mode
    try:
        if not args.no_prewarm:
            model.synthesize_stream('准备好了。', 'warm', lambda a, s: None)
        report['warm'] = memory(); report['samples'] = []
        for text in texts:
            chunks = []; first = []; start = time.perf_counter()
            def receive(audio, rate):
                if not first: first.append(time.perf_counter()-start)
                chunks.append(audio.copy())
            model.synthesize_stream(text, 'test', receive)
            pcm = np.concatenate(chunks)
            report['samples'].append(dict(text=text, samples=len(pcm),
                sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
                firstChunkSeconds=round(first[0], 3), seconds=round(time.perf_counter()-start, 3),
                startBuffer=getattr(model,'last_start_buffer',None),
                memory=memory()))
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        model.close()


if __name__ == '__main__':
    main()
