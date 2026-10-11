import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('check_audio', Path(__file__).resolve().parents[1]/'scripts/check_audio.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ContentCheckTests(unittest.TestCase):
    def test_real_failed_output_is_rejected(self):
        self.assertGreater(check.character_error_rate('我会乖乖等你。', '小刷我刚还我'), .2)

    def test_punctuation_does_not_reject_correct_content(self):
        self.assertEqual(check.character_error_rate('我会乖乖等你。', '我会乖乖等你'), 0)

    def test_missing_and_repeated_content_is_rejected(self):
        for actual in ('', '我会', '我会乖乖等你我会乖乖等你'):
            self.assertGreater(check.character_error_rate('我会乖乖等你。', actual), .2)
