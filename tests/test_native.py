import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from coopanion_soft_voice import native_engine


class NativeValidationTests(unittest.TestCase):
    def test_changed_runtime_file_is_rejected_before_device_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root/'engine.dll'; binary.write_bytes(b'changed')
            (root/'native-runtime.json').write_text(json.dumps({
                'dll': str(binary), 'dllSha256': hashlib.sha256(b'original').hexdigest()}))
            with patch.object(native_engine, 'integrated_device') as probe:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    native_engine.settings(root)
                probe.assert_not_called()

    def test_missing_named_igpu_does_not_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); blob = root/'test.bin'; blob.write_bytes(b'fixture')
            digest = hashlib.sha256(b'fixture').hexdigest()
            (root/'native-runtime.json').write_text(json.dumps({
                'dll':str(blob),'model':str(blob),'codec':str(blob),'dllSha256':digest,
                'deviceName':'Missing integrated GPU'}))
            with patch.dict(native_engine.MODEL_HASHES, {'model':digest,'codec':digest}), \
                 patch.object(native_engine, 'integrated_device', side_effect=RuntimeError('No integrated GPU')):
                with self.assertRaisesRegex(RuntimeError, 'No integrated GPU'):
                    native_engine.settings(root)
