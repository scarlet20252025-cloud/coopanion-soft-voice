import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from coopanion_soft_voice import voice_pack as vp
from coopanion_soft_voice.config import reference, REFERENCE_TEXT

class VoicePackTests(unittest.TestCase):
    def test_create_import_load_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); z=root/'voice.zip'
            vp.create(reference(),z,'example-voice','示例音色',REFERENCE_TEXT)
            first=vp.install(z,root/'voices');second=vp.install(z,root/'voices')
            self.assertEqual(first,second)
            audio,manifest=vp.load(root/'voices'/first['key'])
            self.assertEqual(audio.read_bytes(),reference().read_bytes())
            self.assertEqual(manifest['referenceText'],REFERENCE_TEXT)

    def test_reject_traversal_duplicate_and_extra_entries(self):
        for names in [['../voice.json','reference.wav'],['voice.json','voice.json'],['voice.json','reference.wav','run.py']]:
            with self.subTest(names=names),tempfile.TemporaryDirectory() as d:
                z=Path(d)/'bad.zip'
                with zipfile.ZipFile(z,'w') as f:
                    for name in names:f.writestr(name,'x')
                with self.assertRaises(ValueError):vp.read_zip(z)

    def test_tampered_audio_and_unsupported_language(self):
        with tempfile.TemporaryDirectory() as d:
            z=Path(d)/'a.zip';m=vp.create(reference(),z,'test-voice','测试',REFERENCE_TEXT)
            with self.assertRaises(ValueError):vp.validate(m,b'bad')
            m['language']='English'
            with self.assertRaises(ValueError):vp.validate(m,reference().read_bytes())

    def test_changed_transcript_has_distinct_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            vp.create(reference(),root/'a.zip','test-voice','测试',REFERENCE_TEXT)
            vp.create(reference(),root/'b.zip','test-voice','测试',REFERENCE_TEXT+'呀')
            self.assertNotEqual(vp.install(root/'a.zip',root/'voices')['key'],vp.install(root/'b.zip',root/'voices')['key'])
