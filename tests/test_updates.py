import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from coopanion_soft_voice import updates

class UpdateTests(unittest.TestCase):
    def test_update_descriptor_accepts_own_technical_release_only(self):
        with tempfile.TemporaryDirectory() as folder:
            _,_,release=self.fixture(Path(folder))
            release['patch']['url']=release['patch']['url'].replace('/download/v','/download/updates-v')
            updates.descriptor(release)
            release['patch']['url']=release['patch']['url'].replace(updates.REPO,'elsewhere/untrusted')
            with self.assertRaisesRegex(ValueError,'Untrusted'):updates.descriptor(release)

    def fixture(self,root,extra=None):
        site=root/'python/Lib/site-packages/coopanion_soft_voice';site.mkdir(parents=True)
        (site/'__init__.py').write_text("__version__='0.4.11'\n")
        (root/'portable-manifest.json').write_text(json.dumps({'version':'0.4.11'}))
        (root/'native-runtime.json').write_text(json.dumps({'dllSha256':'abc','speechOnly':{'hashes':{'model':'def','codec':'ghi'}}}))
        (root/'model.gguf').write_bytes(b'keep-model')
        (root/'settings.json').write_bytes(b'keep-settings')
        files={'python/coopanion_soft_voice/__init__.py':b"__version__='0.5.0'\n",'world/package.json':b'{"name":"cortico-world-soft-voice","version":"0.4.0"}'}
        files.update(extra or {})
        meta={'format':1,'version':'0.5.0','worldVersion':'0.4.0','runtimeHashes':{'dll':'abc','model':'def','codec':'ghi'},'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
        archive=root/'patch.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,data in files.items():z.writestr(name,data)
            z.writestr('patch-manifest.json',json.dumps(meta))
        release={'format':1,'platform':'windows-x64','version':'0.5.0','worldVersion':'0.4.0','minimumVersion':'0.4.11','patch':{'file':'coopanion-voice-update-0.5.0.zip','bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'url':f'https://github.com/{updates.REPO}/releases/download/v0.5.0/coopanion-voice-update-0.5.0.zip'}}
        return site,archive,release

    def test_code_update_preserves_models_settings_and_has_a_backup(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'emit'):
            root=Path(folder);site,archive,release=self.fixture(root)
            updates.install_archive(root,archive,release,verify=lambda:None)
            self.assertIn('0.5.0',(site/'__init__.py').read_text())
            self.assertEqual((root/'model.gguf').read_bytes(),b'keep-model')
            self.assertEqual((root/'settings.json').read_bytes(),b'keep-settings')
            self.assertEqual(json.loads((root/'portable-manifest.json').read_text())['version'],'0.5.0')
            self.assertFalse((root/'updates/pending.json').exists())
            self.assertTrue(list((root/'updates/backups').rglob('*')))

    def test_failed_verification_restores_exact_previous_bytes_and_removes_new_files(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(updates,'emit'):
            root=Path(folder);site,archive,release=self.fixture(root)
            before=(site/'__init__.py').read_bytes()
            def fail():raise RuntimeError('simulated doctor failure')
            with self.assertRaisesRegex(RuntimeError,'doctor failure'):updates.install_archive(root,archive,release,verify=fail)
            self.assertEqual((site/'__init__.py').read_bytes(),before)
            self.assertFalse((root/'world/package.json').exists())
            self.assertEqual(json.loads((root/'portable-manifest.json').read_text())['version'],'0.4.11')

    def test_checksum_or_unsafe_member_cannot_modify_installation(self):
        for extra in [{},{'../outside.py':b'pass'},{'models/replaced.gguf':b'no'}]:
            with tempfile.TemporaryDirectory() as folder,patch.object(updates,'emit'):
                root=Path(folder);site,archive,release=self.fixture(root,extra)
                if not extra:release['patch']['sha256']='0'*64
                with self.assertRaises(ValueError):updates.install_archive(root,archive,release,verify=lambda:None)
                self.assertIn('0.4.11',(site/'__init__.py').read_text())

    def test_different_profile_and_untrusted_url_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);site,archive,release=self.fixture(root)
            release['patch']['url']='https://example.com/patch.zip'
            with self.assertRaises(ValueError):updates.descriptor(release)
            release['patch']['url']=f'https://github.com/{updates.REPO}/releases/download/v0.5.0/coopanion-voice-update-0.5.0.zip'
            (root/'native-runtime.json').write_text(json.dumps({'dllSha256':'changed'}))
            with self.assertRaisesRegex(ValueError,'incompatible'):updates.install_archive(root,archive,release,verify=lambda:None)

    def test_downgrade_and_unreviewed_source_deployment_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);site,archive,release=self.fixture(root)
            (root/'portable-manifest.json').write_text('{"version":"0.5.1"}')
            with self.assertRaisesRegex(ValueError,'downgrade'):updates.install_archive(root,archive,release,verify=lambda:None)
            with self.assertRaisesRegex(ValueError,'portable package Python'):updates.portable(root)

    def market(self,root,world_version='0.3.11'):
        ext=root/'extensions';pkg=ext/'node_modules/cortico-world-soft-voice';pkg.mkdir(parents=True)
        (pkg/'src').mkdir();(pkg/'src/obsolete.js').write_text('old code')
        (pkg/'package.json').write_text(json.dumps({'name':'cortico-world-soft-voice','version':world_version}))
        (ext/'package.json').write_text(json.dumps({'dependencies':{'cortico-world-soft-voice':world_version,'other-world':'1.2.3'}}))
        return ext,pkg

    def test_market_only_install_updates_without_local_mirror_and_rolls_back_exactly(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as d,patch.object(updates,'emit'):
                root=Path(d);site,archive,release=self.fixture(root,{'world/src/new.js':b'new'})
                ext,pkg=self.market(root);registration=(ext/'package.json').read_bytes()
                self.assertEqual(updates.world_targets(ext),[pkg.resolve()])
                def verify():
                    if fail:raise RuntimeError('verification failed')
                if fail:
                    with self.assertRaises(RuntimeError):updates.install_archive(root,archive,release,ext,verify)
                    self.assertEqual((ext/'package.json').read_bytes(),registration)
                    self.assertTrue((pkg/'src/obsolete.js').exists());self.assertFalse((pkg/'src/new.js').exists())
                else:
                    updates.install_archive(root,archive,release,ext,verify)
                    self.assertEqual((pkg/'src/new.js').read_bytes(),b'new');self.assertFalse((pkg/'src/obsolete.js').exists())
                    self.assertEqual(json.loads((ext/'package.json').read_text())['dependencies'],{'cortico-world-soft-voice':'0.4.0','other-world':'1.2.3'})
                self.assertFalse((ext/'local-soft-voice').exists())

    def test_world_only_update_and_newer_market_world_are_handled_separately(self):
        with tempfile.TemporaryDirectory() as d,patch.object(updates,'emit'):
            root=Path(d);site,archive,release=self.fixture(root)
            (root/'portable-manifest.json').write_text('{"version":"0.5.0"}')
            ext,pkg=self.market(root)
            updates.install_archive(root,archive,release,ext,verify=lambda:None)
            self.assertEqual(updates.installed_world_version(root,ext),'0.4.0')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);site,archive,release=self.fixture(root);ext,pkg=self.market(root,'9.0.0')
            with self.assertRaisesRegex(ValueError,'downgrade'):updates.install_archive(root,archive,release,ext,verify=lambda:None)
            self.assertEqual(updates.installed_world_version(root,ext),'9.0.0')
