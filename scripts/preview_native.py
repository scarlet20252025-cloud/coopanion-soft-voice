"""Generate a candidate WAV using the configured production engine; never auto-play."""
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
from coopanion_soft_voice.cli import load
from coopanion_soft_voice.speech_text import model_speech_pieces


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', default='.runtime-native')
    p.add_argument('--text', default='今天也辛苦啦，先喝一点水，放松一下肩膀。等你准备好了，我们再一起复习数学，把不懂的地方慢慢弄明白，好不好？')
    p.add_argument('--output', default='preview.wav')
    args = p.parse_args()
    if not args.text.strip() or len(args.text) > 60:
        p.error('Use 1-60 characters for a preview')
    model = load(Path(args.runtime).resolve(), 'igpu')
    try:
        chunks = []
        for piece in model_speech_pieces(model,args.text):
            model.synthesize_stream(piece, 'accepted', lambda audio, rate: chunks.append(audio.copy()))
        out = Path(args.output).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, np.concatenate(chunks), 24000, subtype='PCM_16')
        print('Saved (not played):', out)
    finally:
        model.close()


if __name__ == '__main__':
    main()
