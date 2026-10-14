import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_setup', ROOT/'scripts/setup_native.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_cache_is_revalidated_and_corrupt_download_never_published(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'source'; source.write_bytes(b'correct')
            dest = Path(d)/'dest'
            digest = hashlib.sha256(b'correct').hexdigest()
            setup.download(source.as_uri(), dest, digest)
            with patch.object(setup.urllib.request, 'urlopen', side_effect=AssertionError('network')):
                setup.download(source.as_uri(), dest, digest)
            dest.write_bytes(b'bad-cache'); source.write_bytes(b'bad-server')
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                setup.download(source.as_uri(), dest, digest)
            self.assertEqual(dest.read_bytes(), b'bad-cache')
            self.assertFalse(dest.with_name('dest.partial').exists())

    def test_archive_cannot_escape_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); archive = root/'a.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../outside', 'bad')
            with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
                setup.extract(archive, root/'out')
            self.assertFalse((root/'outside').exists())

    def test_published_setup_has_no_author_machine_paths(self):
        for name in ('setup_native.py', 'setup-native.ps1', 'preview_native.py', 'deploy.ps1',
                     'prepare_speech_profile.py', 'verify_deployment.py', 'install_world.py',
                     'activate_portable.py','install-portable.ps1','find-coopanion.ps1','build_portable.py'):
            text = (ROOT/'scripts'/name).read_text(encoding='utf-8')
            self.assertNotIn('63526', text)
            self.assertNotIn('coopanion-native-trial', text)
