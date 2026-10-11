"""Exact-text, fixed-voice playback. Never falls back to model inference."""
import argparse
import hashlib
import io
import json
import time
import wave
from pathlib import Path

from .config import REFERENCE_SHA256


def lookup(root, text):
    root = Path(root).resolve()
    index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
    if index['reference_sha256'] != REFERENCE_SHA256:
        raise ValueError('Cached voice does not match the accepted reference')
    item = index['phrases'].get(text.strip())
    if item is None:
        return None
    path = (root / item['file']).resolve()
    if path.parent != root:
        raise ValueError('Invalid cache path')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise ValueError('Cached audio checksum mismatch')
    with wave.open(io.BytesIO(data)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (24000, 1, 2):
            raise ValueError('Expected 24 kHz mono PCM16')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('text')
    args = parser.parse_args()
    start = time.perf_counter()
    data = lookup(args.cache, args.text)
    result = {'hit': data is not None, 'lookup_ms': round((time.perf_counter()-start)*1000, 3),
              'inference': False, 'gpu': False}
    print(json.dumps(result), flush=True)
    if data is not None and not args.check_only:
        import winsound
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)


if __name__ == '__main__':
    main()
