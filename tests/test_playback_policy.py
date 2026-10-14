"""A slow producer must not put gaps into playback or alter the accepted samples."""
import tempfile,unittest
from unittest.mock import patch,Mock
import numpy as np
from coopanion_soft_voice import playback,pcm_player

class PlaybackPolicyTests(unittest.TestCase):
    def run_case(self,mode,rtf):
        out=[];started=[];status=Mock(output_underflow=False)
        actual=pcm_player.PCMPlayer
        def make_player(**kw):
            p=actual(**kw);original=p.push
            def tick():
                a=np.zeros((480,1),dtype=np.float32)
                try:p._callback(a,480,None,status)
                except pcm_player.sd.CallbackStop:p.finished.set()
                if np.any(a):out.extend(a[:,0])
            def push(a,rate):original(a,rate);tick();tick()
            p.push=push
            finish=p.finish
            def drain():
                p.producer_done=True;p.start_playback()
                while not p.finished.is_set():tick()
                finish()
            p.finish=drain
            started.append(p)
            return p
        class Model:
            sample_rate=24000;buffer_mode='adaptive';speech_piece_limit=32
            last_start_buffer={'productionRtf':rtf}
            def synthesize_stream(self,text,key,receive,on_complete=None):
                for _ in range(4):receive(np.full(480,.25,dtype=np.float32),24000)
        with tempfile.TemporaryDirectory() as root,patch.object(pcm_player.sd,'OutputStream'),patch.object(playback,'PCMPlayer',make_player):
            result=playback.speak(Model(),'你好呀','accepted',100,1,'test',lambda *a,**k:None,root,mode)
        return result,out,started[0]

    def test_slow_gpu_auto_buffers_the_whole_reply_without_gaps(self):
        result,audio,_=self.run_case('auto',3.4)
        self.assertEqual(result['effectivePlaybackMode'],'buffered')
        self.assertEqual(result['underrunMs'],0)
        self.assertTrue(result['smoothPlayback'])
        np.testing.assert_array_equal(audio,np.full(1920,.25,dtype=np.float32))

    def test_fast_gpu_retains_streaming_and_reports_actual_starvation(self):
        result,_,_=self.run_case('auto',.45)
        self.assertEqual(result['effectivePlaybackMode'],'stream')
        self.assertGreater(result['underrunMs'],0)
        self.assertFalse(result['smoothPlayback'])

    def test_explicit_modes_and_unknown_cadence(self):
        for mode,rtf,effective in [('buffered',.4,'buffered'),('stream',4,'stream'),('auto',None,'buffered')]:
            result,_,_=self.run_case(mode,rtf)
            self.assertEqual(result['effectivePlaybackMode'],effective)

    def test_invalid_mode_cannot_create_audio_device(self):
        with patch.object(playback,'PCMPlayer') as factory:
            with self.assertRaises(ValueError):playback.speak(None,'test','accepted',65,1,'test',None,'.','invalid')
            factory.assert_not_called()
