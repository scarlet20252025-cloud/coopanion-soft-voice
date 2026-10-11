"""CPU-only content screening; passing does not establish pleasantness or voice identity."""
import argparse
import json
import os
from pathlib import Path
import sys
import unicodedata


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).lower() if c.isalnum())


def character_error_rate(expected, actual):
    expected, actual = normalize(expected), normalize(actual)
    if not expected:
        raise ValueError('Expected transcript cannot be empty')
    previous = list(range(len(actual) + 1))
    for i, a in enumerate(expected, 1):
        current = [i]
        for j, b in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (a != b)))
        previous = current
    return previous[-1] / len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', required=True)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--whisper-model', required=True)
    parser.add_argument('--dependency-dir')
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if args.dependency_dir:
        sys.path.append(args.dependency_dir)
    import torch
    import whisper
    import soundfile as sf
    import librosa
    import numpy as np
    torch.set_num_threads(2)
    audio, rate = sf.read(args.audio, dtype='float32')
    if audio.ndim != 1 or not len(audio) or not np.isfinite(audio).all():
        raise ValueError('Empty, multichannel or nonfinite audio')
    model = whisper.load_model(args.whisper_model, device='cpu')
    result = model.transcribe(librosa.resample(audio, orig_sr=rate, target_sr=16000),
                              language='zh', fp16=False, temperature=0, condition_on_previous_text=False)
    cer = character_error_rate(args.expected, result['text'])
    clipping = float(np.mean(np.abs(audio) >= .999))
    report = {'expected': args.expected, 'asr': result['text'], 'character_error_rate': cer,
              'clipping_fraction': clipping, 'seconds': len(audio)/rate,
              'content_check_passed': cer <= .2 and clipping < .01,
              'voice_quality_approved': False, 'asr_device': 'cpu'}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
