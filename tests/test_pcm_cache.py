import unittest
import numpy as np
from coopanion_soft_voice.pcm_cache import PCMCache


class PCMCacheTests(unittest.TestCase):
    def test_byte_bounded_lru_preserves_exact_immutable_samples(self):
        cache=PCMCache(32)
        a=np.arange(4,dtype=np.float32);b=a+10;c=a+20
        cache.put('a',[a]);cache.put('b',[b]);self.assertEqual(cache.bytes,32)
        self.assertEqual(cache.get('a')[0].tobytes(),a.tobytes())
        cache.put('c',[c]);self.assertIsNone(cache.get('b'))
        with self.assertRaises(ValueError):cache.get('a')[0][0]=99
        cache.put('oversized',[np.zeros(9,dtype=np.float32)])
        self.assertEqual(cache.bytes,32);self.assertEqual(cache.status()['entries'],2)
        cache.clear();self.assertEqual(cache.bytes,0);self.assertEqual(len(cache.entries),0)

    def test_replacement_accounts_for_old_bytes_and_disabled_capacity(self):
        cache=PCMCache(32);cache.put('a',[np.zeros(4,dtype=np.float32)])
        cache.put('a',[np.zeros(2,dtype=np.float32)])
        self.assertEqual(cache.bytes,8)
        empty=PCMCache(0);empty.put('a',[np.zeros(1,dtype=np.float32)])
        self.assertEqual(empty.bytes,0)
