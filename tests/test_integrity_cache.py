import hashlib
import tempfile
import unittest
from pathlib import Path
from coopanion_soft_voice.integrity_cache import verify


class IntegrityTests(unittest.TestCase):
    def test_hit_and_changes_and_forced_check(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model'; cache=Path(d)/'cache'; path.write_bytes(b'first')
            digest=hashlib.sha256(b'first').hexdigest()
            self.assertFalse(verify(path,digest,cache))
            self.assertTrue(verify(path,digest,cache))
            self.assertFalse(verify(path,digest))
            path.write_bytes(b'other')
            with self.assertRaises(ValueError): verify(path,digest,cache)

    def test_corrupt_receipt_rehashed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'model'; cache=Path(d)/'cache'; path.write_bytes(b'x')
            digest=hashlib.sha256(b'x').hexdigest(); verify(path,digest,cache)
            next(cache.glob('*.json')).write_text('bad json')
            self.assertFalse(verify(path,digest,cache))
