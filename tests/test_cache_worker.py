import io
import json
import subprocess
import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from coopanion_soft_voice.cache_worker import worker, doctor
from coopanion_soft_voice.cache_worker import cache_root
from coopanion_soft_voice.phrase_cache import lookup
from coopanion_soft_voice.config import REFERENCE_TEXT
import wave


class CacheWorkerTests(unittest.TestCase):
    def run_worker(self, messages):
        output = io.StringIO()
        with patch('coopanion_soft_voice.cache_worker.play') as unused:
            calls=[]
            worker(io.StringIO('\n'.join(json.dumps(x) for x in messages)), output,
                   player=lambda data, volume: calls.append((len(data),volume)))
            unused.assert_not_called()
        return [json.loads(x[len('@@COSY@@'):]) for x in output.getvalue().splitlines()], calls

    def test_hit_miss_invalid_then_recovery(self):
        result,calls=self.run_worker([
            {'id':'hit','text':REFERENCE_TEXT,'volume':35},
            {'id':'miss','text':'uncached phrase'},
            {'id':'bad','text':REFERENCE_TEXT,'volume':101},
            {'id':'recover','text':REFERENCE_TEXT,'volume':0},
            {'type':'quit'},
            {'id':'after-quit','text':REFERENCE_TEXT}])
        self.assertEqual(len(calls),2)
        self.assertEqual([v for _,v in calls],[35,0])
        self.assertTrue(any(x.get('id')=='miss' and x.get('skipped') for x in result))
        self.assertTrue(any(x.get('id')=='bad' and x['type']=='error' for x in result))
        self.assertFalse(any(x.get('id')=='after-quit' for x in result))

    def test_fresh_process_does_not_import_torch(self):
        result=subprocess.run([sys.executable,'-c',
            "import sys; from coopanion_soft_voice.cache_worker import doctor; doctor(); "
            "assert 'torch' not in sys.modules; assert 'numpy' not in sys.modules"],
            capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_packaged_files_verified(self):
        self.assertEqual(doctor()['phrases'],3)

    def test_combination_preserves_audio_and_adds_only_pause(self):
        one=lookup(cache_root(),REFERENCE_TEXT)
        joined=lookup(cache_root(),REFERENCE_TEXT+'\n'+REFERENCE_TEXT)
        with wave.open(io.BytesIO(one)) as wav:frames=wav.readframes(wav.getnframes())
        with wave.open(io.BytesIO(joined)) as wav:
            self.assertEqual(wav.readframes(wav.getnframes()),frames+b'\x00\x00'*4800+frames)
        self.assertIsNone(lookup(cache_root(),REFERENCE_TEXT+'没有缓存的另一句话。'))
        self.assertIsNone(lookup(cache_root(),REFERENCE_TEXT*17))

    def test_unknown_suffix_and_changed_reference_never_play(self):
        messages,calls=self.run_worker([
            {'id':'partial','text':REFERENCE_TEXT+'unknown'},
            {'id':'voice','text':REFERENCE_TEXT,'referenceAudio':'wrong.wav'}])
        self.assertEqual(calls,[])
        self.assertTrue(any(x.get('id')=='voice' and x['type']=='error' for x in messages))
