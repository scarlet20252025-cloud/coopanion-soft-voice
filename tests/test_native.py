import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from coopanion_soft_voice import native_engine
import ctypes as C
from unittest.mock import Mock


class FakeNative:
    samples = 1920
    def qt_tts_default_params(self, p): pass
    def qt_synthesize(self, ctx, p, out):
        pcm = (C.c_float * self.samples)()
        if self.samples: p._obj.on_chunk(pcm, self.samples, None)
        return 0
    def qt_audio_free(self, out): pass
    def qt_last_error(self): return b'native failure'


class NativeValidationTests(unittest.TestCase):
    def test_trailing_whitespace_does_not_create_an_empty_synthesis_piece(self):
        from coopanion_soft_voice import playback
        import numpy as np
        class Player:
            def __init__(self, **kwargs):
                self.samples=0; self.rate=24000; self.first_audio_at=None
                self.underrun_frames=0; self.device_underflows=0
            def push(self, audio, rate): self.samples+=len(audio)
            def finish(self): pass
            def abort(self): pass
        model=Mock(sample_rate=24000)
        def synth(text, key, receive, on_complete):
            if not text.strip(): raise ValueError('empty piece')
            receive(np.zeros(100),24000)
            if on_complete:on_complete()
        model.synthesize_stream.side_effect=synth
        with tempfile.TemporaryDirectory() as folder, patch.object(playback,'PCMPlayer',Player):
            playback.speak(model,'字'*60+'\n','accepted',0,1,'test',lambda *a,**k:None,folder)
        self.assertEqual(model.synthesize_stream.call_count,1)

    def test_capped_and_empty_outputs_fail_without_completing_then_recover(self):
        engine = native_engine.NativeEngine.__new__(native_engine.NativeEngine)
        engine.ctx = 1; engine.voice = native_engine.Voice(); engine.dll = FakeNative()
        completed = Mock()
        for size, error in [(360*1920, 'generation limit'), (0, 'no audio')]:
            engine.dll.samples = size
            with self.assertRaisesRegex(RuntimeError, error):
                engine.synthesize_stream('测试。', 'accepted', lambda a,r:None, completed)
            completed.assert_not_called()
        engine.dll.samples = 1920
        received = []
        engine.synthesize_stream('恢复。', 'accepted', lambda a,r:received.append(len(a)), completed)
        self.assertEqual(received, [1920])
        completed.assert_called_once()

    def test_callback_failure_is_propagated_without_completion(self):
        engine = native_engine.NativeEngine.__new__(native_engine.NativeEngine)
        engine.ctx = 1; engine.voice = native_engine.Voice(); engine.dll = FakeNative()
        engine.dll.samples = 28800
        completed = Mock()
        with self.assertRaisesRegex(RuntimeError, 'device failed'):
            engine.synthesize_stream('测试。', 'accepted', Mock(side_effect=OSError('device failed')), completed)
        completed.assert_not_called()

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
