import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('world_installer',ROOT/'scripts/install_world.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class WorldInstallTests(unittest.TestCase):
    def test_newer_extension_is_not_downgraded_but_model_profile_is_connected(self):
        for linked in (False,True):
            with self.subTest(marketplace=linked),tempfile.TemporaryDirectory() as d:
                root=Path(d);ext=root/'extensions';bot=root/'bot';runtime=root/'runtime'
                ext.mkdir();bot.mkdir();runtime.mkdir()
                (ext/'package.json').write_text(json.dumps({'dependencies':{installer.NAME:'9.0.0'}}))
                (bot/'config.json').write_text('{"worlds":{}}')
                actual=ext/('node_modules/.pnpm/pkg/node_modules' if linked else 'node_modules')/installer.NAME
                installer.copy_package(ROOT/'world',actual)
                meta=json.loads((actual/'package.json').read_text(encoding='utf-8'));meta['version']='9.0.0'
                (actual/'package.json').write_text(json.dumps(meta),encoding='utf-8')
                (actual/'src/future.js').write_text('newer code')
                if linked:
                    try:(ext/'node_modules'/installer.NAME).symlink_to(actual,target_is_directory=True)
                    except OSError as error:self.skipTest(str(error))
                with patch.object(installer.subprocess,'run'):plan=installer.install(ext,bot,runtime)
                self.assertEqual(plan['action'],'skip')
                self.assertEqual((actual/'src/future.js').read_text(),'newer code')
                self.assertEqual(json.loads((ext/'package.json').read_text())['dependencies'][installer.NAME],'9.0.0')
                self.assertEqual(json.loads((ext/'local-soft-voice/package.json').read_text())['version'],'9.0.0')
                self.assertEqual(json.loads((bot/'data/soft-voice/runtime-profile.json').read_text())['runtime'],str(runtime.resolve()))

    def test_old_version_updates_equal_version_skips_and_corrupt_equal_version_repairs(self):
        with tempfile.TemporaryDirectory() as d:
            ext=Path(d);target=ext/'node_modules'/installer.NAME
            installer.copy_package(ROOT/'world',target)
            self.assertEqual(installer.installation_plan(ext)['action'],'skip')
            (target/'src/index.js').write_text('corrupt')
            self.assertEqual(installer.installation_plan(ext)['action'],'repair')
            meta=json.loads((target/'package.json').read_text(encoding='utf-8'));meta['version']='0.0.1'
            (target/'package.json').write_text(json.dumps(meta))
            self.assertEqual(installer.installation_plan(ext)['action'],'update')
            self.assertLess(installer.semantic_version('1.0.0-beta.9'),installer.semantic_version('1.0.0'))

    def test_update_preserves_existing_speech_choice(self):
        for enabled in [True,False]:
            with self.subTest(enabled=enabled),tempfile.TemporaryDirectory() as d:
                root=Path(d);ext=root/'extensions';bot=root/'bot';runtime=root/'runtime'
                ext.mkdir();bot.mkdir();runtime.mkdir();data=bot/'data/soft-voice';data.mkdir(parents=True)
                (ext/'package.json').write_text('{"dependencies":{}}');(bot/'config.json').write_text('{"worlds":{}}')
                (data/'settings.json').write_text(json.dumps({'speechEnabled':enabled,'config':{'syncBubbles':False,'volume':37}}))
                with patch.object(installer.subprocess,'run'):installer.install(ext,bot,runtime)
                saved=json.loads((data/'settings.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['speechEnabled'],enabled);self.assertEqual(saved['config'],{'syncBubbles':False,'volume':37})

    def test_fresh_install_contains_model_profile_and_preserves_personal_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);ext=root/'extensions';bot=root/'bot';runtime=root/'runtime'
            ext.mkdir();bot.mkdir();runtime.mkdir()
            (ext/'package.json').write_text(json.dumps({'dependencies':{'other-world':'1.0'}}))
            (bot/'config.json').write_text(json.dumps({'personal':'keep','worlds':{}}))
            with patch.object(installer.subprocess,'run'):installer.install(ext,bot,runtime,True)
            meta=json.loads((ext/'node_modules'/installer.NAME/'package.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['version'],json.loads((ROOT/'world/package.json').read_text(encoding='utf-8'))['version'])
            self.assertTrue((ext/'node_modules'/installer.NAME/meta['cortico']['webUiClient']).is_file())
            cfg=json.loads((bot/'config.json').read_text(encoding='utf-8'));self.assertEqual(cfg['personal'],'keep')
            self.assertEqual(json.loads((ext/'package.json').read_text(encoding='utf-8'))['dependencies']['other-world'],'1.0')
            self.assertEqual(json.loads((ext/'package.json').read_text(encoding='utf-8'))['dependencies'][installer.NAME],meta['version'])
            profile=json.loads((bot/'data/soft-voice/runtime-profile.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(profile['runtime']),runtime.resolve())
            self.assertTrue(json.loads((bot/'data/soft-voice/settings.json').read_text(encoding='utf-8'))['speechEnabled'])

    def test_package_replacement_breaks_hardlink_without_changing_old_store(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';target=root/'target';source.mkdir();target.mkdir()
            for part in ['src','dist']:(source/part).mkdir()
            for name in ['package.json','LICENSE','README.md']:(source/name).write_text('new')
            (source/'package.json').write_text(json.dumps({'name':installer.NAME,'version':'1.0.0'}))
            store=root/'store.json';store.write_text('old');os.link(store,target/'package.json')
            installer.copy_package(source,target)
            self.assertEqual(json.loads((target/'package.json').read_text(encoding='utf-8'))['version'],'1.0.0')
            self.assertEqual(store.read_text(encoding='utf-8'),'old')

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
