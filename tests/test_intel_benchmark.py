import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('intel_benchmark', Path(__file__).resolve().parents[1] / 'scripts/benchmark_intel_issue13.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class IntelBenchmarkTests(unittest.TestCase):
    def test_baseline_does_not_inherit_tuning(self):
        parent = {'PATH': 'keep', 'GGML_VK_FORCE_MMVQ': '1', 'QWEN_CPU_THREADS': '8'}
        self.assertNotIn('GGML_VK_FORCE_MMVQ', bench.trial_environment(parent, 'baseline'))
        self.assertEqual(parent['QWEN_CPU_THREADS'], '8')
        self.assertEqual(bench.trial_environment(parent, 'submit-1000')['GGML_VK_MAX_NODES_PER_SUBMIT'], '1000')

    def test_excludes_warmup_and_weights_by_audio_duration(self):
        report = {'cases': [{'ok': True, 'ms': 10000, 'seconds': 1},
                            {'ok': True, 'ms': 1000, 'seconds': 2},
                            {'ok': True, 'ms': 4000, 'seconds': 8}]}
        result = bench.summarize(report, '[Perf] CodePredictor 112.5 ms (4.1 ms/frame)')
        self.assertEqual(result['warmRtf'], .5)
        self.assertEqual(result['stagesMs']['CodePredictor'], [112.5])

    def test_different_baseline_pcm_blocks_equivalence(self):
        before = {'valid': True, 'warmRtf': 1, 'pcm': ['a']}
        after = {**before, 'pcm': ['b']}
        result = bench.compare(before, before, after)
        self.assertFalse(result['baselinePcmStable'])
        self.assertFalse(result['candidatePcmMatches'])
        self.assertFalse(result['acceptedForRelease'])

    def test_incomplete_run_has_no_performance_claim(self):
        failed = bench.summarize({'cases': [{'ok': False, 'seconds': 0}]}, '')
        self.assertFalse(failed['valid'])
        self.assertIsNone(bench.compare(failed, failed, failed)['warmRtfChangePercent'])
