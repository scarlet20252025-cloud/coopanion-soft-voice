import ctypes as C
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from coopanion_soft_voice import reference_cache as cache
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.native_abi import Voice


class ReferenceCacheTests(unittest.TestCase):
    def test_lossless_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cache.json'
            values = [C.c_float((i-512)/735).value for i in range(1024)]
            codes = [i % 2048 for i in range(16*55)]
            cache.write(path, values, codes, 55)
            self.assertEqual(cache.read(path), (values, codes, 55))
            path.write_text(path.read_text().replace('735', '736'))
            # Explicit truncation always invalidates the document.
            path.write_text(path.read_text()[:50])
            self.assertIsNone(cache.read(path))

    def test_bounds_and_nonfinite_features_rejected(self):
        for bad in (float('nan'), float('inf'), 1e100):
            with self.assertRaises(ValueError):
                cache.validate(dict(embedding=[bad]*1024, codes=[0]*16, frames=1))
        with self.assertRaises(ValueError):
            cache.validate(dict(embedding=[0]*1024, codes=[2048]*16, frames=1))

    def test_identity_tracks_reference_and_engine(self):
        with tempfile.TemporaryDirectory() as d:
            ref = Path(d)/'ref.wav'; ref.write_bytes(b'first')
            cfg = dict(dllSha256='a', model='m', codec='c')
            first = cache.cache_path(d, cfg, ref)
            ref.write_bytes(b'second')
            self.assertNotEqual(first, cache.cache_path(d, cfg, ref))
            second = cache.cache_path(d, cfg, ref)
            cfg['dllSha256'] = 'b'
            self.assertNotEqual(second, cache.cache_path(d, cfg, ref))

    def test_python_owned_arrays_never_native_freed(self):
        model = NativeEngine.__new__(NativeEngine)
        model.ctx = 1; model.dll = Mock(); model.dirs = []; model.voice = Voice()
        model.cached_arrays = ([1], [2])
        model.close()
        model.dll.qt_voice_ref_free.assert_not_called()
        model.dll.qt_free.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
