"""Model-free Coopanion worker. Cache misses stay silent, never trigger inference."""
import array
import io
import json
import math
import sys
import time
import wave
from pathlib import Path
from .phrase_cache import lookup
from .config import reference


def cache_root():
    return Path(__file__).parent / 'assets' / 'phrase-cache'


def doctor():
    index = json.loads((cache_root()/'index.json').read_text(encoding='utf-8'))
    for text in index['phrases']:
        lookup(cache_root(), text)
    return {'ok': True, 'backend': 'cache-only', 'gpu': False,
            'phrases': len(index['phrases']), 'sampleRate': 24000}


def play(data, volume):
    # Change only this sound's PCM amplitude, never system/session volume.
    with wave.open(io.BytesIO(data)) as wav:
        frames = array.array('h', wav.readframes(wav.getnframes()))
    frames = array.array('h', (round(sample*volume/100) for sample in frames))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(frames.tobytes())
    import winsound
    winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY | winsound.SND_NODEFAULT)


def worker(input_stream=None, output_stream=None, player=play):
    input_stream = input_stream if input_stream is not None else sys.stdin
    output_stream = output_stream if output_stream is not None else sys.stdout
    def emit(message):
        print('@@COSY@@'+json.dumps(message, ensure_ascii=False), file=output_stream, flush=True)
    emit({'type': 'ready', 'device': '原声缓存 / 不使用 GPU', 'preflight': doctor()})
    for line in input_stream:
        request_id = None
        try:
            message = json.loads(line)
            if message.get('type') == 'quit':
                break
            request_id = str(message.get('id', ''))
            if not request_id:
                raise ValueError('Missing request id')
            supplied=message.get('referenceAudio')
            if supplied and Path(supplied).resolve()!=reference():
                raise ValueError('Reference voice is locked')
            volume = float(message.get('volume', 65))
            if not math.isfinite(volume) or not 0 <= volume <= 100:
                raise ValueError('Invalid volume')
            if float(message.get('speed', 1)) != 1:
                raise ValueError('Cached voice uses original speed only')
            started = time.perf_counter()
            data = lookup(cache_root(), str(message.get('text', '')))
            if data is None:
                emit({'type': 'status', 'stage': 'cache_miss', 'detail': '游戏模式：未缓存的回复仅显示文字'})
                emit({'type': 'done', 'id': request_id, 'seconds': 0, 'skipped': True,
                      'reason': 'cache_miss', 'playbackMode': 'cache-only'})
                continue
            with wave.open(io.BytesIO(data)) as wav:
                seconds = wav.getnframes()/wav.getframerate()
            emit({'type': 'status', 'stage': 'playing', 'id': request_id,
                  'detail': '播放原声缓存', 'synthesisMs': 0})
            player(data, volume)
            emit({'type': 'done', 'id': request_id, 'seconds': seconds,
                  'totalSynthesisMs': 0, 'elapsedMs': round((time.perf_counter()-started)*1000),
                  'playbackMode': 'cache-only'})
        except Exception as exc:
            emit({'type': 'error', 'id': request_id, 'stage': 'cache', 'error': str(exc)})


if __name__ == '__main__':
    worker()
