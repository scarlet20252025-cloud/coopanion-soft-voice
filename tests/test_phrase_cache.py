import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))

from coopanion_soft_voice.config import REFERENCE_SHA256
from coopanion_soft_voice.phrase_cache import lookup


class CacheTests(unittest.TestCase):
    def test_exact_match_corruption_and_voice_lock(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            data = io.BytesIO()
            with wave.open(data, 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * 240)
            blob = data.getvalue()
            (root/'one.wav').write_bytes(blob)
            index = {'reference_sha256': REFERENCE_SHA256, 'phrases': {
                'hello': {'file': 'one.wav', 'sha256': hashlib.sha256(blob).hexdigest()}}}
            def save():
                (root/'index.json').write_text(json.dumps(index), encoding='utf-8')
            save()
            self.assertEqual(lookup(root, 'hello'), blob)
            self.assertIsNone(lookup(root, 'hello there'))
            (root/'one.wav').write_bytes(b'broken')
            with self.assertRaises(ValueError): lookup(root, 'hello')
            index['reference_sha256'] = 'different voice'
            save()
            with self.assertRaises(ValueError): lookup(root, 'hello')
