import unittest
from coopanion_soft_voice.start_buffer import StartBuffer


class BufferTests(unittest.TestCase):
    def test_fast_production_starts_earlier_without_prefill_bias(self):
        b=StartBuffer()
        values=[b.feed(1920, 5+i*.04) for i in range(4)]
        self.assertEqual(values,[False,False,False,True])

    def test_slow_or_jittery_production_keeps_larger_reserve(self):
        b=StartBuffer()
        for i in range(4): ready=b.feed(1920,i*.11)
        self.assertFalse(ready); self.assertEqual(b.target_seconds,1.2)

    def test_fixed_mode_retains_original_1200ms_gate(self):
        b=StartBuffer(fixed=True)
        for i in range(14): self.assertFalse(b.feed(1920,i*.04))
        self.assertTrue(b.feed(1920,.56))
