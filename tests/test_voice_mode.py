import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('voice_mode',Path(__file__).resolve().parents[1]/'scripts/voice_mode.py')
mode=importlib.util.module_from_spec(spec);spec.loader.exec_module(mode)


class VoiceModeTests(unittest.TestCase):
    def test_switch_preserves_settings_and_backs_up_previous_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'.cosyvoice-tts';root.mkdir()
            model=Path(d)/'clone-model';model.mkdir();(model/'config.json').write_text('{}')
            original={'runtime':d,'mode':'cache','extra':'preserve'}
            profile=root/'softvoice-profile.json';profile.write_text(json.dumps(original))
            settings=root/'settings.json';settings.write_text('{"speechEnabled": false, "config": {"volume": 31}}')
            before=settings.read_bytes()
            result=mode.select_mode(d,'gpu')
            self.assertTrue(result['restartRequired'])
            self.assertFalse(result['speechEnabled'])
            self.assertEqual(settings.read_bytes(),before)
            self.assertEqual(json.loads((Path(result['backup'])/profile.name).read_text()),original)
            self.assertEqual(json.loads(profile.read_text())['extra'],'preserve')
            self.assertFalse(mode.select_mode(d,'gpu')['restartRequired'])
            mode.select_mode(d,'cache');before=profile.read_bytes()
            (model/'config.json').unlink()
            with self.assertRaises(ValueError):mode.select_mode(d,'gpu')
            self.assertEqual(profile.read_bytes(),before)
