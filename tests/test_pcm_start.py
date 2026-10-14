import unittest
from unittest.mock import Mock, patch
import numpy as np
from coopanion_soft_voice import pcm_player


class PCMStartTests(unittest.TestCase):
    def test_preopened_silence_is_not_an_underrun_and_tail_is_not_cut(self):
        with patch.object(pcm_player.sd,'OutputStream') as stream:
            p=pcm_player.PCMPlayer()
            stream.return_value.start.assert_called_once()
            status=Mock(output_underflow=False); out=np.empty((480,1),dtype=np.float32)
            p._callback(out,480,None,status)
            self.assertEqual(p.underrun_frames,0)
            p.producer_done=True
            p._callback(out,480,None,status)  # final short tail has not been enqueued yet
            p.push(np.ones(480,dtype=np.float32),24000)
            with self.assertRaises(pcm_player.sd.CallbackStop):p._callback(out,480,None,status)
            self.assertTrue(np.all(out==1));p.abort()

    def test_real_starvation_after_first_audio_is_counted(self):
        with patch.object(pcm_player.sd,'OutputStream'):
            p=pcm_player.PCMPlayer();out=np.empty((480,1),dtype=np.float32)
            status=Mock(output_underflow=False)
            p.push(np.ones(480,dtype=np.float32),24000)
            p._callback(out,480,None,status);p._callback(out,480,None,status)
            self.assertEqual(p.underrun_frames,480);p.abort()
