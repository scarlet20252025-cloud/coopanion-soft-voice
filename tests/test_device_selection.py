"""Portable device selection must never pick a discrete GPU implicitly."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from coopanion_soft_voice import native_engine as engine

spec = importlib.util.spec_from_file_location('activate_portable', ROOT / 'scripts' / 'activate_portable.py')
activate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activate)

GTX = {'index': 0, 'name': 'NVIDIA GeForce GTX 1660', 'kind': 'discrete', 'vendorId': 4318}
UHD = {'index': 1, 'name': 'Intel(R) UHD Graphics 630', 'kind': 'integrated', 'vendorId': 32902}
IRIS = {'index': 2, 'name': 'Intel(R) Iris(R) Xe Graphics', 'kind': 'integrated', 'vendorId': 32902}


class DeviceSelectionTests(unittest.TestCase):
    def setUp(self):
        self._engine = engine.vulkan_devices
        self._activate = activate.vulkan_devices

    def tearDown(self):
        engine.vulkan_devices = self._engine
        activate.vulkan_devices = self._activate

    def detect(self, devices):
        engine.vulkan_devices = lambda: list(devices)
        activate.vulkan_devices = lambda: list(devices)

    def test_single_integrated_gpu_is_selected_automatically(self):
        self.detect([GTX, UHD])
        self.assertEqual(engine.select_integrated_name(), UHD['name'])

    def test_discrete_only_machine_is_told_which_flag_to_use(self):
        self.detect([GTX])
        with self.assertRaises(RuntimeError) as caught:
            engine.select_integrated_name()
        message = str(caught.exception)
        self.assertIn(GTX['name'], message)
        self.assertIn('-DeviceName', message)
        self.assertIn('没有核显', message)

    def test_a_named_discrete_gpu_is_not_returned_by_the_integrated_helper(self):
        self.detect([GTX])
        with self.assertRaises(RuntimeError):
            engine.select_integrated_name(GTX['name'])

    def test_multiple_integrated_gpus_ask_the_user_to_choose(self):
        self.detect([UHD, IRIS])
        with self.assertRaises(RuntimeError) as caught:
            engine.select_integrated_name()
        self.assertIn('多个核显', str(caught.exception))

    def test_missing_gpu_points_at_the_graphics_driver(self):
        self.detect([])
        with self.assertRaises(RuntimeError) as caught:
            engine.select_integrated_name()
        self.assertIn('驱动', str(caught.exception))

    def test_inventory_lists_every_gpu_for_the_installer_prompt(self):
        self.detect([GTX, UHD])
        report = activate.inventory()
        self.assertEqual(report['integrated'], [UHD['name']])
        self.assertEqual([d['name'] for d in report['devices']], [GTX['name'], UHD['name']])


if __name__ == '__main__':
    unittest.main()
