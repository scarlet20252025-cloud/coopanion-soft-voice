import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('world_installer',ROOT/'scripts/install_world.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class WorldInstallTests(unittest.TestCase):
    def test_update_preserves_existing_speech_choice(self):
        for enabled in [True,False]:
            with self.subTest(enabled=enabled),tempfile.TemporaryDirectory() as d:
                root=Path(d);ext=root/'extensions';bot=root/'bot';runtime=root/'runtime'
                ext.mkdir();bot.mkdir();runtime.mkdir();data=bot/'data/soft-voice';data.mkdir(parents=True)
                (ext/'package.json').write_text('{"dependencies":{}}');(bot/'config.json').write_text('{"worlds":{}}')
                (data/'settings.json').write_text(json.dumps({'speechEnabled':enabled,'config':{'syncBubbles':False,'volume':37}}))
                with patch.object(installer.subprocess,'run'):installer.install(ext,bot,runtime)
                saved=json.loads((data/'settings.json').read_text())
                self.assertEqual(saved['speechEnabled'],enabled);self.assertEqual(saved['config'],{'syncBubbles':False,'volume':37})

    def test_fresh_install_contains_model_profile_and_preserves_personal_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ext=root/'extensions';bot=root/'bot';runtime=root/'runtime'
            ext.mkdir();bot.mkdir();runtime.mkdir()
            (ext/'package.json').write_text(json.dumps({'dependencies':{'other-world':'1.0'}}))
            (bot/'config.json').write_text(json.dumps({'personal':'keep','worlds':{}}))
            with patch.object(installer.subprocess,'run'):installer.install(ext,bot,runtime,True)
            meta=json.loads((ext/'node_modules'/installer.NAME/'package.json').read_text())
            self.assertEqual(meta['version'],'0.3.10')
            self.assertTrue((ext/'node_modules'/installer.NAME/meta['cortico']['consoleClient']).is_file())
            cfg=json.loads((bot/'config.json').read_text());self.assertEqual(cfg['personal'],'keep')
            self.assertEqual(json.loads((ext/'package.json').read_text())['dependencies']['other-world'],'1.0')
            profile=json.loads((bot/'data/soft-voice/runtime-profile.json').read_text())
            self.assertEqual(Path(profile['runtime']),runtime.resolve())
            self.assertTrue(json.loads((bot/'data/soft-voice/settings.json').read_text())['speechEnabled'])

    def test_package_replacement_breaks_hardlink_without_changing_old_store(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';target=root/'target';source.mkdir();target.mkdir()
            for part in ['src','dist']:(source/part).mkdir()
            for name in ['package.json','LICENSE','README.md']:(source/name).write_text('new')
            store=root/'store.json';store.write_text('old');os.link(store,target/'package.json')
            installer.copy_package(source,target)
            self.assertEqual((target/'package.json').read_text(),'new')
            self.assertEqual(store.read_text(),'old')

    def test_pnpm_alias_resolves_only_within_its_own_store(self):
        with tempfile.TemporaryDirectory() as d:
            ext=Path(d)/'extensions';store=ext/'node_modules/.pnpm/pkg/node_modules'/installer.NAME
            store.mkdir(parents=True);alias=ext/'node_modules'/installer.NAME
            try:alias.symlink_to(store,target_is_directory=True)
            except OSError as e:self.skipTest('Directory symlink unavailable: '+str(e))
            self.assertEqual(installer.package_target(ext),store.resolve())
            alias.unlink();outside=Path(d)/installer.NAME;outside.mkdir();alias.symlink_to(outside,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'outside'):installer.package_target(ext)


if __name__=='__main__':unittest.main()
