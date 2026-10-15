import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load('run_gpu_diagnostic')
builder = load('build_gpu_diagnostic')


class DiagnosticKitTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell bootstrap')
    def test_windows_bootstrap_failure_still_creates_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'kit.zip'
            builder.build(archive)
            with zipfile.ZipFile(archive) as z:
                z.extractall(root)
            kit = root / 'QingHe-Intel-Diagnostic'
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(kit / 'scripts/start_gpu_diagnostic.ps1'),
                                     '-Runtime', str(root / 'missing'), '-NoPause'],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            reports = list((kit / 'reports').glob('*.zip'))
            self.assertEqual(len(reports), 1)
            with zipfile.ZipFile(reports[0]) as z:
                status = json.loads(z.read('status.json').decode('utf-8-sig'))
                self.assertFalse(status['success'])
                self.assertEqual(status['stage'], 'bootstrap')

    def test_selects_intel_not_discrete(self):
        intel = {'kind': 'integrated', 'vendorId': 0x8086, 'name': 'Intel UHD'}
        nvidia = {'kind': 'discrete', 'vendorId': 0x10de, 'name': 'RTX'}
        self.assertEqual(tool.choose_device([nvidia, intel]), 'Intel UHD')
        for devices in ([nvidia], [intel, intel]):
            with self.assertRaises(RuntimeError):
                tool.choose_device(devices)
        with self.assertRaises(RuntimeError):
            tool.choose_device([nvidia], 'RTX')

    def test_profile_isolated_and_paths_resolved(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp) / '安装目录'; runtime.mkdir()
            for name in ('engine.dll', 'model.gguf', 'codec.gguf'):
                (runtime / name).write_bytes(b'fixture')
            cfg = {'dll': 'engine.dll', 'model': 'model.gguf', 'codec': 'codec.gguf', 'dllSha256': 'test'}
            profile = runtime / 'native-runtime.json'; profile.write_text(json.dumps(cfg))
            before = profile.read_bytes()
            dest = Path(temp) / 'isolated'
            tool.isolated_profile(runtime, dest)
            self.assertEqual(profile.read_bytes(), before)
            isolated = json.loads((dest / 'native-runtime.json').read_text())
            self.assertEqual(Path(isolated['model']), (runtime / 'model.gguf').resolve())
            self.assertEqual(len(list(runtime.iterdir())), 4)

    def test_archive_excludes_secrets_profiles_and_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); trials = folder / 'trials'; trials.mkdir()
            (trials / 'runtime-profile.json').write_text('{"password":"do-not-send"}')
            (trials / 'voice.wav').write_bytes(b'audio')
            (trials / 'one.log').write_text('path C:\\Users\\Alice\\model\nAuthorization: Bearer secret-value\n[Perf] Total 10 ms')
            (trials / 'comparison.json').write_text('{"valid":true}')
            archive = folder / 'out.zip'
            tool.pack_report(folder, archive, {'success': False})
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
                self.assertNotIn('trials/runtime-profile.json', names)
                self.assertNotIn('trials/voice.wav', names)
                text = z.read('trials/one.log').decode()
                self.assertNotIn('Alice', text)
                self.assertNotIn('secret-value', text)
                self.assertIn('[Perf] Total 10 ms', text)

    def test_deliverable_contains_bootstrap_and_no_model(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'kit.zip'
            result = builder.build(file)
            self.assertGreater(result['bytes'], 0)
            self.assertEqual(len(result['sha256']), 64)
            with zipfile.ZipFile(file) as z:
                self.assertIn('QingHe-Intel-Diagnostic/START.cmd', z.namelist())
                self.assertFalse(any(n.endswith(('.gguf', '.dll', '.pyc')) for n in z.namelist()))
                self.assertTrue(z.read('QingHe-Intel-Diagnostic/scripts/start_gpu_diagnostic.ps1').startswith(b'\xef\xbb\xbf'))
