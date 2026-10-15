"""Isolated Vulkan A/B/A trials. Never changes the installed runtime or selects a GPU.

All speech is synthesized to local WAV files, not played. No reports are uploaded.
The first utterance of EACH process is warmup, not a cold-start comparison.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

VARIANTS = {
    'baseline': {},
    'submit-1000': {'GGML_VK_MAX_NODES_PER_SUBMIT': '1000'},
    'mmvq': {'GGML_VK_FORCE_MMVQ': '1'},
}
TEXTS = ['我在这里陪你呀，慢慢来，不着急。',
         '今天也辛苦啦，先喝一点水，放松一下肩膀。',
         '我在这里陪你呀，慢慢来，不着急。']


def trial_environment(parent, variant):
    # Prevent an inherited experiment from contaminating the baseline.
    env = {k: v for k, v in parent.items()
           if not k.upper().startswith(('GGML_VK_', 'QWEN_'))}
    env.update(PYTHONIOENCODING='utf-8', OPENBLAS_NUM_THREADS='1')
    env.update(VARIANTS[variant])
    return env


def summarize(report, log):
    cases = report.get('cases', [])
    valid = bool(cases) and all(c.get('ok') and c.get('seconds', 0) > 0 for c in cases)
    warm = cases[1:] if valid else []
    duration = sum(c['seconds'] for c in warm)
    ms = sum(c['ms'] for c in warm)
    stages = {}
    for stage in ('Prefill', 'TalkerDecode', 'CodePredictor', 'CodecDecode'):
        stages[stage] = [float(x) for x in re.findall(r'\[Perf\] ' + stage + r' (\d+(?:\.\d+)?) ms', log)]
    return {'valid': valid, 'warmRtf': ms / 1000 / duration if duration else None,
            'warmSynthesisMs': ms, 'warmAudioSeconds': duration,
            'pcm': [c.get('pcmSha256') for c in cases],
            'firstChunkMs': [c.get('firstChunkMs') for c in cases],
            'peaks': report.get('peaks'), 'stagesMs': stages}


def compare(before, candidate, after):
    valid = all(x['valid'] and x['warmRtf'] is not None for x in (before, candidate, after))
    stable = bool(before['pcm']) and before['pcm'] == after['pcm']
    same = stable and candidate['pcm'] == before['pcm']
    baseline = (before['warmRtf'] + after['warmRtf']) / 2 if valid else None
    return {'valid': valid, 'baselinePcmStable': stable, 'candidatePcmMatches': same,
            'warmRtfChangePercent': (candidate['warmRtf'] / baseline - 1) * 100 if baseline else None,
            'baselineWarmRtfRange': [before['warmRtf'], after['warmRtf']],
            'acceptedForRelease': False,
            'note': 'Exploration only; requires repeated target-device, playback and voice acceptance. '
                    'RTF changes with different PCM are not a controlled speedup.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, help='Directory containing native-runtime.json')
    parser.add_argument('--device', required=True, help='Exact Vulkan GPU name; no automatic fallback')
    parser.add_argument('--output', required=True, help='New local report directory')
    parser.add_argument('--variants', nargs='+', choices=['submit-1000', 'mmvq'], default=['submit-1000', 'mmvq'])
    parser.add_argument('--timeout', type=int, default=900, help='Seconds per trial')
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'src'))
    from coopanion_soft_voice.diagnostics import static_info
    runtime = Path(args.runtime).resolve()
    cfg = json.loads((runtime / 'native-runtime.json').read_text(encoding='utf-8'))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = output / 'cases.json'
    cases.write_text(json.dumps(TEXTS, ensure_ascii=False), encoding='utf-8')
    result = {'device': args.device, 'hardware': static_info(), 'nativeSha256': cfg['dllSha256'],
              'casesSha256': hashlib.sha256(cases.read_bytes()).hexdigest(),
              'modelHashes': cfg.get('speechOnly', {}).get('hashes', {}),
              'installedConfigurationModified': False, 'playbackValidated': False,
              'runs': [], 'comparisons': []}
    try:
        sequence = ['baseline', *args.variants, 'baseline']
        for index, variant in enumerate(sequence):
            label = f'{index}-{variant}'
            print(f'[{index+1}/{len(sequence)}] {label}: {args.device}', flush=True)
            command = [sys.executable, str(root / 'scripts/benchmark_speech_recovery.py'),
                       '--source', str(root / 'src'), '--runtime', str(runtime),
                       '--device', args.device, '--cases', str(cases), '--output', str(output / label)]
            begun = time.monotonic()
            with (output / f'{label}.log').open('w', encoding='utf-8') as log:
                completed = subprocess.run(command, env=trial_environment(os.environ, variant),
                                           stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            if completed.returncode:
                raise RuntimeError(f'{label} failed ({completed.returncode}); see local log. No fallback attempted.')
            report = json.loads((output / label / 'report.json').read_text(encoding='utf-8'))
            summary = summarize(report, (output / f'{label}.log').read_text(encoding='utf-8'))
            if not summary['valid']:
                raise RuntimeError(f'{label}: incomplete synthesis; stop comparisons.')
            result['runs'].append({'label': label, 'variant': variant, 'environment': VARIANTS[variant],
                                   'elapsedSeconds': round(time.monotonic()-begun, 2), **summary})
        result['comparisons'] = [
            {'variant': r['variant'], **compare(result['runs'][0], r, result['runs'][-1])}
            for r in result['runs'][1:-1]]
    except Exception as exc:
        result['error'] = str(exc)
        raise
    finally:
        (output / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Local report: {output / "comparison.json"}', flush=True)


if __name__ == '__main__':
    main()
