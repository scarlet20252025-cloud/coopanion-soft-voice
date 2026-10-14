"""Build an exact-weight, fixed-reference speech-only runtime without changing the active app."""
import argparse
import json
import shutil
from pathlib import Path
from strip_speech_weights import strip, digest, inspect
from coopanion_soft_voice.native_engine import settings, NativeEngine, MODEL_HASHES
from coopanion_soft_voice.config import reference
from coopanion_soft_voice import reference_cache


def verify_retained(source, target):
    _, _, _, sd, st = inspect(source)
    _, _, _, td, tt = inspect(target)
    source_tensors = {t['name']: t for t in st}
    import hashlib
    def span(f, start, length):
        f.seek(start); h = hashlib.sha256()
        while length:
            block = f.read(min(length, 1024*1024))
            if not block: raise ValueError('Truncated tensor')
            h.update(block); length -= len(block)
        return h.digest()
    with Path(source).open('rb') as sf, Path(target).open('rb') as tf:
        for t in tt:
            original = source_tensors[t['name']]
            if original['descriptor'][:-8] != t['descriptor'][:-8]:
                raise ValueError('Tensor metadata changed')
            if span(sf, sd+original['offset'], original['length']) != span(tf, td+t['offset'], original['length']):
                raise ValueError('Tensor bytes changed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True); p.add_argument('--output', required=True)
    a = p.parse_args(); root = Path(a.runtime).resolve(); dest = Path(a.output).resolve()
    cfg = settings(root)
    if cfg.get('speechOnly'): raise ValueError('Build from the original full runtime')
    if dest.exists(): raise ValueError('Output already exists; use a new directory')
    cache = reference_cache.cache_path(root, cfg, reference())
    if reference_cache.read(cache) is None:
        model = NativeEngine(root)
        model.close()
    if reference_cache.read(cache) is None: raise ValueError('Reference cache unavailable')
    dest.mkdir(parents=True)
    reports = {}; hashes = {}
    for key, prefix in [('model', ('spk_enc.',)), ('codec', ('tok_enc.',))]:
        source = cfg[key]; target = dest / (key+'-speech-only-Q8.gguf')
        reports[key] = strip(source, target, prefix)
        verify_retained(source, target)
        hashes[key] = digest(target); cfg[key] = str(target)
    shutil.copyfile(cache, dest/'voice-features.json')
    cfg['speechOnly'] = dict(format=1, sourceHashes=MODEL_HASHES, hashes=hashes,
                            referenceSha256=digest(reference()),
                            featuresSha256=digest(dest/'voice-features.json'))
    cfg.pop('deviceIndex', None)
    (dest/'native-runtime.json').write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    (dest/'build-report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps({key:{'before':r['before'],'after':r['after'],'removedTensors':len(r['removed'])}
                      for key,r in reports.items()}, indent=2))


if __name__ == '__main__': main()
