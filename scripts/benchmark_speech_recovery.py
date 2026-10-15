"""Muted synthesis comparison with process RAM/GPU sampling; no live Bot changes."""
import argparse
import os
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--source', required=True)
p.add_argument('--runtime', required=True)
p.add_argument('--device', required=True)
p.add_argument('--cases', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
os.environ['OPENBLAS_NUM_THREADS'] = '1'
sys.path.insert(0, a.source)
import hashlib
import json
import threading
import time
import numpy as np
import soundfile as sf
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.speech_text import model_speech_pieces
from coopanion_soft_voice.memory_metrics import snapshot
from coopanion_soft_voice.gpu_memory import GpuMemory

out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
cases = json.loads(Path(a.cases).read_text(encoding='utf-8'))
samples, stop, phase = [], threading.Event(), ['load']
begun = time.perf_counter()
report = {'device': a.device, 'sampleIntervalMs': 100, 'cases': []}
engine = None
with GpuMemory() as gpu:
    def sample():
        samples.append({'ms': round((time.perf_counter()-begun)*1000), 'phase': phase[0],
                        'process': snapshot(), 'gpu': gpu.snapshot()})
    def monitor():
        while not stop.wait(.1): sample()
    thread = threading.Thread(target=monitor, daemon=True); thread.start()
    try:
        engine = NativeEngine(a.runtime, device_name=a.device,
                              on_stage=lambda name, detail: print('PROGRESS '+detail, flush=True))
        engine.cache_repeated = False
        report.update(loadMs=round((time.perf_counter()-begun)*1000), ready=snapshot(),
                      conditioning=engine.voice_conditioning, settings=engine.runtime_parameters)
        for index, text in enumerate(cases):
            print(f'PROGRESS 测试句 {index+1}/{len(cases)}：正在合成', flush=True)
            phase[0] = f'case-{index}'
            blocks, records, first = [], [], []
            started = time.perf_counter()
            result = {'index': index, 'characters': len(text), 'pieces': records, 'ok': True}
            for part, piece in enumerate(model_speech_pieces(engine, text)):
                piece_start = time.perf_counter(); count = [0]
                def receive(block, rate):
                    if not first: first.append(time.perf_counter()-started)
                    blocks.append(block.copy()); count[0] += len(block)
                item = {'index': part, 'characters': len(piece)}
                try:
                    engine.synthesize_stream(piece, 'benchmark', receive)
                    item['ok'] = True
                except Exception as exc:
                    item.update(ok=False, error=str(exc)); result['ok'] = False
                item.update(ms=round((time.perf_counter()-piece_start)*1000), samples=count[0])
                records.append(item)
                if not item['ok']: break
            pcm = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.float32)
            result.update(ms=round((time.perf_counter()-started)*1000),
                          firstChunkMs=round(first[0]*1000) if first else None,
                          seconds=len(pcm)/24000, pcmSha256=hashlib.sha256(pcm.tobytes()).hexdigest())
            sf.write(out/f'{index}.wav', pcm, 24000, subtype='PCM_16')
            report['cases'].append(result)
            print(json.dumps(result), flush=True)
        phase[0] = 'sleep'; engine.close(); engine = None
        time.sleep(2); sample(); report['sleep'] = snapshot()
    finally:
        if engine: engine.close()
        stop.set(); thread.join(timeout=5)
        report['measurements'] = samples
        report['peaks'] = {key: max((s['process'][key] for s in samples), default=None)
                           for key in ('privateMiB', 'residentMiB', 'peakResidentMiB')}
        report['peaks'].update({key: max((s['gpu'][key] for s in samples if s['gpu'].get(key) is not None), default=None)
                               for key in ('dedicatedMiB', 'sharedMiB')})
        (out/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({'loadMs': report.get('loadMs'), 'peaks': report['peaks'], 'sleep': report.get('sleep')}), flush=True)
