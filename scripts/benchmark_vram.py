"""Isolated, muted VRAM regression: process PDH, speed, PCM and sleep release.

Run baseline/candidate in separate processes; use GGML_VK_MEMORY_LOGGER=1 for
allocation-level corroboration. Sampling measures the observed peak, not an
unobservable absolute maximum. This does not change the installed desktop.
"""
import argparse
import hashlib
import json
import threading
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from coopanion_soft_voice.gpu_memory import GpuMemory
from coopanion_soft_voice.memory_metrics import snapshot
from coopanion_soft_voice.native_engine import NativeEngine, settings


def benchmark(runtime, device, output, texts, repeats):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = settings(runtime, cached_verification=True, device_name=device)
    records, stopped = [], threading.Event()
    phase = ['before-load']
    with GpuMemory() as gpu:
        def sample():
            records.append({'elapsedMs': round((time.perf_counter()-start)*1000),
                            'phase': phase[0], 'gpu': gpu.snapshot(), 'process': snapshot()})
        def monitor():
            while not stopped.wait(.1):
                sample()
        start = time.perf_counter()
        sample()
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        engine = None
        report = {'device': device, 'nativeSha256': cfg['dllSha256'],
                  'sampleIntervalMs': 100, 'cases': [], 'counterScope': 'process-all-adapters'}
        try:
            phase[0] = 'load'
            engine = NativeEngine(runtime, device_name=device)
            report.update(loadMs=round((time.perf_counter()-start)*1000),
                          nativeSettings=engine.runtime_parameters, voiceConditioning=engine.voice_conditioning)
            phase[0] = 'loaded-idle'
            time.sleep(.3)
            for repeat in range(repeats):
                for i, text in enumerate(texts):
                    phase[0] = f'utterance-{repeat}-{i}'
                    chunks, first = [], []
                    begun = time.perf_counter()
                    def receive(a, rate):
                        if not first:
                            first.append(time.perf_counter()-begun)
                        chunks.append(a.copy())
                    engine.synthesize_stream(text, 'vram-regression', receive)
                    elapsed = time.perf_counter()-begun
                    pcm = np.concatenate(chunks)
                    if not np.isfinite(pcm).all():
                        raise ValueError('Nonfinite audio')
                    sf.write(out/f'{repeat}-{i}.wav', pcm, 24000, subtype='PCM_16')
                    report['cases'].append({'repeat': repeat, 'textIndex': i, 'samples': len(pcm),
                        'pcmSha256': hashlib.sha256(pcm.tobytes()).hexdigest(),
                        'synthesisMs': round(elapsed*1000), 'firstChunkMs': round(first[0]*1000),
                        'rtf': round(elapsed/(len(pcm)/24000), 4)})
                    phase[0] = f'idle-{repeat}-{i}'
                    time.sleep(.3)
            phase[0] = 'sleep'
            engine.close()
            engine = None
            # Windows GPU counters can lag buffer release; retain the worker for
            # several counter refreshes rather than labelling a stale value as sleep usage.
            time.sleep(3)
            sample()
            report['ok'] = True
        except BaseException as exc:
            report.update(ok=False, error=str(exc))
            raise
        finally:
            if engine:
                engine.close()
            stopped.set()
            thread.join(timeout=5)
            report['measurements'] = records
            report['observedPeaksMiB'] = {
                key: max((r['gpu'][key] for r in records if r['gpu'].get(key) is not None), default=None)
                for key in ('dedicatedMiB', 'sharedMiB')}
            (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k: v for k, v in report.items() if k != 'measurements'}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True)
    p.add_argument('--device', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--texts')
    p.add_argument('--repeats', type=int, choices=range(1, 4), default=2)
    a = p.parse_args()
    texts = json.loads(Path(a.texts).read_text(encoding='utf-8')) if a.texts else [
        '我在这里陪你呀，慢慢来，不着急。',
        '今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？']
    if not isinstance(texts, list) or not 1 <= len(texts) <= 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 60 for t in texts):
        p.error('texts must be 1-20 strings of 1-60 characters')
    benchmark(a.runtime, a.device, a.output, texts, a.repeats)
