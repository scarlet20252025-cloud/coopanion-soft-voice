"""Exact-text, fixed-voice playback. Never falls back to model inference."""
import argparse
import hashlib
import io
import json
import time
import wave
from pathlib import Path

from .config import REFERENCE_SHA256


def lookup(root, text, _compose=True):
    root = Path(root).resolve()
    index = json.loads((root / 'index.json').read_text(encoding='utf-8'))
    if index['reference_sha256'] != REFERENCE_SHA256:
        raise ValueError('Cached voice does not match the accepted reference')
    item = index['phrases'].get(text.strip())
    if item is None:
        if not _compose or len(text)>4000:
            return None
        remaining=text.strip(); parts=[]
        phrases=sorted(index['phrases'],key=len,reverse=True)
        while remaining:
            match=next((phrase for phrase in phrases if phrase and remaining.startswith(phrase)),None)
            if match is None:return None
            parts.append(lookup(root,match,_compose=False))
            remaining=remaining[len(match):].lstrip()
            if len(parts)>16:return None
        if not parts:return None
        output=io.BytesIO()
        with wave.open(output,'wb') as wav:
            wav.setparams((1,2,24000,0,'NONE','not compressed'))
            for i,data in enumerate(parts):
                if i:wav.writeframes(b'\x00\x00'*4800)
                with wave.open(io.BytesIO(data)) as source:
                    wav.writeframes(source.readframes(source.getnframes()))
        return output.getvalue()
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
