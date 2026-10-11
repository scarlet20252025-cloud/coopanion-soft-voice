import ast,importlib.util,json,sys,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from coopanion_soft_voice.config import reference,manifest,MODEL_REVISION,validate_model
spec=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install_plugin.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class PackageTests(unittest.TestCase):
    def test_accepted_reference_integrity_and_audio_format(self):
        with wave.open(str(reference())) as wav:
            self.assertEqual(wav.getframerate(),24000)
            self.assertEqual(wav.getnchannels(),1)
            self.assertEqual(wav.getsampwidth(),2)
            self.assertGreater(wav.getnframes(),24000)

    def test_missing_model_cannot_pass_preflight(self):
        self.assertEqual(manifest()['revision'],MODEL_REVISION)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):validate_model(d)

    def test_all_python_sources_compile(self):
        for folder in ('src','scripts'):
            for p in (ROOT/folder).rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))

    def test_unknown_plugin_source_rejected(self):
        with self.assertRaises(ValueError):installer.patch_runtime('unexpected upstream version')

    def test_cache_install_preserves_settings_and_stays_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();(root/'runtime').mkdir();(root/'.cosyvoice-tts').mkdir()
            (root/'package.json').write_text(json.dumps({'name':'cortico-world-cosyvoice-tts','version':'0.1.11'}))
            (root/'src/runtime.js').write_text((ROOT/'tests/fixtures/runtime.js').read_text(encoding='utf-8'),encoding='utf-8')
            settings=root/'.cosyvoice-tts/settings.json'
            settings.write_text(json.dumps({'speechEnabled':False,'config':{'volume':27,'maxQueue':2}}))
            with patch.object(installer.subprocess,'run'):
                installer.install(root,root/'no-model','cache',False)
            result=json.loads(settings.read_text(encoding='utf-8'))
            self.assertFalse(result['speechEnabled'])
            self.assertEqual(result['config']['volume'],27)
            self.assertEqual(result['config']['maxQueue'],2)
            self.assertNotIn('referenceAudio',result)
            profile=json.loads((root/'.cosyvoice-tts/softvoice-profile.json').read_text())
            self.assertEqual(profile['mode'],'cache')

    def test_install_and_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();(root/'runtime').mkdir();(root/'.cosyvoice-tts').mkdir()
            fixture=(ROOT/'tests/fixtures/runtime.js').read_text(encoding='utf-8')
            original={'package.json':json.dumps({'name':'cortico-world-cosyvoice-tts','version':'0.1.11'}),
                      'src/runtime.js':fixture,'runtime/worker.py':'# previous worker\n',
                      'runtime/preflight.py':'# previous preflight\n',
                      '.cosyvoice-tts/settings.json':json.dumps({'volume':42,'custom':'preserve'})}
            for p,text in original.items():(root/p).write_text(text,encoding='utf-8')
            with patch.object(installer.subprocess,'run'):
                installer.install(root,root/'models')
            changed=(root/'src/runtime.js').read_text(encoding='utf-8')
            self.assertEqual(installer.patch_runtime(changed),changed)
            cfg=json.loads((root/'.cosyvoice-tts/settings.json').read_text(encoding='utf-8'))
            self.assertEqual(cfg['custom'],'preserve');self.assertEqual(cfg['config']['speed'],1)
            backup=next((root/'.cosyvoice-tts/softvoice-backups').iterdir())
            installer.restore(backup)
            for p,text in original.items():self.assertEqual((root/p).read_text(encoding='utf-8'),text)
            self.assertFalse((root/'.cosyvoice-tts/softvoice-profile.json').exists())

if __name__=='__main__':unittest.main()
