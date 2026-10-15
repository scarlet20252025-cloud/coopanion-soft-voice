import ctypes as C
import unittest
from coopanion_soft_voice.gpu_memory import CounterValue, CounterItem, process_total


class GpuMemoryTests(unittest.TestCase):
    def test_process_accounting_excludes_other_processes_and_invalid_counters(self):
        items = [('pid_123_luid_0x0_0x1_phys_0', 0, 100),
                 ('pid_123_luid_0x0_0x2_phys_0', 1, 50),
                 ('pid_1234_luid_0x0_0x1_phys_0', 0, 900),
                 ('pid_123_luid_0x0_0x3_phys_0', 0xc0000bc6, 1000),
                 ('pid_123_luid_0x0_0x4_phys_0', 0, -1)]
        self.assertEqual(process_total(items, 123), 150)

    def test_unavailable_does_not_mean_zero(self):
        self.assertIsNone(process_total([], 123))
        self.assertEqual(process_total([('pid_123_luid_0_1_phys_0', 0, 0)], 123), 0)

    def test_windows_64_bit_structure_layout(self):
        self.assertEqual(C.sizeof(CounterValue), 16)
        if C.sizeof(C.c_void_p) == 8:
            self.assertEqual(C.sizeof(CounterItem), 24)
