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


def fake_engine():
    engine = native_engine.NativeEngine.__new__(native_engine.NativeEngine)
    engine.reference_text = native_engine.REFERENCE_TEXT; engine.ctx = 1; engine.dll = FakeNative()
    engine.cached_arrays = ((C.c_float*1024)(),(C.c_int32*(16*55))())
    engine.voice = native_engine.Voice(engine.cached_arrays[0],1024,engine.cached_arrays[1],55,16)
    engine._conditioning_signature = engine.conditioning_signature()
    return engine


class NativeValidationTests(unittest.TestCase):
    def test_progressive_cache_is_opt_in_and_clears_stale_process_environment(self):
        import os
        config={'deviceType':'integrated','kvContext':1024,'adaptiveKv':True}
        with patch.dict(os.environ,{},clear=True):
            self.assertTrue(native_engine.configure_vulkan(config)['adaptiveKv'])
            self.assertEqual(os.environ['QWEN_TTS_ADAPTIVE_KV'],'1')
            self.assertFalse(native_engine.configure_vulkan({**config,'adaptiveKv':False})['adaptiveKv'])
            self.assertNotIn('QWEN_TTS_ADAPTIVE_KV',os.environ)

    def test_nvidia_uses_device_local_without_changing_uma_default(self):
        import os
        config={'deviceType':'discrete','vendorId':0x10de,'kvContext':1024,'compactGraphs':True,'streamTextEmbedding':True}
        with patch.dict(os.environ,{},clear=True):
            policy=native_engine.configure_vulkan(config)
            self.assertEqual(policy['memoryPolicy'],'device-local')
            self.assertEqual(os.environ['GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM'],'1')
        with patch.dict(os.environ,{},clear=True):
            policy=native_engine.configure_vulkan({**config,'deviceType':'integrated','vendorId':0x1002})
            self.assertEqual(policy['memoryPolicy'],'backend-default')
            self.assertNotIn('GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM',os.environ)
    def test_explicit_discrete_selection_is_allowed_without_automatic_fallback(self):
        devices=[{'index':0,'name':'NVIDIA','kind':'discrete'},{'index':1,'name':'AMD','kind':'integrated'}]
        with patch.object(native_engine,'vulkan_devices',return_value=devices):
            self.assertEqual(native_engine.integrated_devices(),[{'index':1,'name':'AMD'}])
            self.assertEqual(native_engine.explicit_device('NVIDIA')['index'],0)
            with self.assertRaisesRegex(RuntimeError,'no automatic fallback'):native_engine.explicit_device('Missing GPU')
            with self.assertRaises(RuntimeError):native_engine.select_integrated_name('NVIDIA')
    def test_auto_device_selection_never_chooses_discrete_or_ambiguous_devices(self):
        with patch.object(native_engine,'integrated_devices',return_value=[{'index':1,'name':'Intel Integrated'}]):
            self.assertEqual(native_engine.select_integrated_name(),'Intel Integrated')
            self.assertEqual(native_engine.integrated_device('Intel Integrated'),1)
            with self.assertRaises(RuntimeError):native_engine.select_integrated_name('NVIDIA Discrete')
        for devices in [[],[{'index':0,'name':'A'},{'index':1,'name':'B'}]]:
            with patch.object(native_engine,'integrated_devices',return_value=devices):
                with self.assertRaises(RuntimeError):native_engine.select_integrated_name()
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
        model=Mock(sample_rate=24000,speech_piece_limit=60,speech_piece_target=None)
        def synth(text, key, receive, on_complete):
            if not text.strip(): raise ValueError('empty piece')
            receive(np.zeros(100),24000)
            if on_complete:on_complete()
        model.synthesize_stream.side_effect=synth
        with tempfile.TemporaryDirectory() as folder, patch.object(playback,'PCMPlayer',Player):
            playback.speak(model,'字'*60+'\n','accepted',0,1,'test',lambda *a,**k:None,folder)
        self.assertEqual(model.synthesize_stream.call_count,1)

    def test_capped_and_empty_outputs_fail_without_completing_then_recover(self):
        engine = fake_engine()
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
        engine = fake_engine()
        engine.dll.samples = 28800
        completed = Mock()
        with self.assertRaisesRegex(RuntimeError, 'device failed'):
            engine.synthesize_stream('测试。', 'accepted', Mock(side_effect=OSError('device failed')), completed)
        completed.assert_not_called()

    def test_short_final_piece_is_enqueued_before_playback_completion(self):
        engine=fake_engine();engine.dll.samples=1920
        events=[]
        engine.synthesize_stream('嗯。','accepted',lambda a,r:events.append('audio'),lambda:events.append('done'))
        self.assertEqual(events,['audio','done'])

    def test_missing_or_changed_reference_fails_before_generating(self):
        engine=fake_engine();engine.dll.qt_synthesize=Mock()
        engine.voice.ref_codes[0]=1
        with self.assertRaisesRegex(RuntimeError,'conditioning changed'):
            engine.synthesize_stream('测试。','accepted',Mock())
        engine.dll.qt_synthesize.assert_not_called()
        engine.voice=native_engine.Voice()
        with self.assertRaisesRegex(RuntimeError,'fallback is disabled'):
            engine.synthesize_stream('测试。','accepted',Mock())
        engine.dll.qt_synthesize.assert_not_called()

    def test_long_playback_finishes_once_after_all_reconditioned_pieces(self):
        from coopanion_soft_voice import playback
        import numpy as np
        class Player:
            def __init__(self,**kwargs):
                self.samples=0;self.rate=24000;self.first_audio_at=None
                self.underrun_frames=0;self.device_underflows=0;self.producer_done=False
            def push(self,a,rate):
                self.assert_not_done=not self.producer_done
                if not self.assert_not_done:raise AssertionError('player ended before final audio')
                self.samples+=len(a)
            def finish(self):
                if not self.producer_done:raise AssertionError('missing final completion')
            def abort(self):pass
        calls=[];model=Mock(sample_rate=24000,speech_piece_limit=32,speech_piece_target=24)
        def synth(text,key,receive,on_complete):
            calls.append(bool(on_complete));receive(np.zeros(1920),24000)
            if on_complete:on_complete()
        model.synthesize_stream.side_effect=synth
        text='可以这么比喻，但不是“死了又活过来”——我没有持续的主观体验，也不会在两次对话之间感到时间流逝。更准确地说，收到消息时系统才运行这一轮，生成回复；没人问时，我没有在后台醒着思考。'
        with tempfile.TemporaryDirectory() as folder,patch.object(playback,'PCMPlayer',Player):
            result=playback.speak(model,text,'accepted',0,1,'test',lambda *a,**k:None,folder)
        self.assertEqual(calls,[False,False,False,True])
        self.assertEqual(result['pieceCount'],4)
        self.assertEqual([p['characters'] for p in result['pieces']],[20,28,25,16])

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
