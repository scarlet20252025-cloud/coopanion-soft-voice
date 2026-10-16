import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('bubble_installer',Path(__file__).resolve().parents[1]/'scripts/install_bubble_bridge.py')
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

class BubbleBridgeInstallerTests(unittest.TestCase):
    def test_reversible_installer_rejects_changed_official_page(self):
        with tempfile.TemporaryDirectory(prefix='soft-voice-bubble-test-') as work:
            package=Path(work)/'pet'
            (package/'web').mkdir(parents=True)
            (package/'package.json').write_text(json.dumps({'version':'0.1.4'}))
            original='\n'.join(before for before,_after in helper.HOOKS)
            page=package/'web/pet-app.js'
            page.write_text(original,encoding='utf-8')
            helper.install_bridge(package)
            changed=page.read_text(encoding='utf-8')
            self.assertIn(helper.MARKER,changed)
            helper.install_bridge(package)
            self.assertEqual(page.read_text(encoding='utf-8'),changed)
            helper.install_bridge(package,True)
            self.assertEqual(page.read_text(encoding='utf-8'),original)
            page.write_text(original.replace('function closeBubble()', 'function changedBubble()'),encoding='utf-8')
            with self.assertRaises(ValueError):helper.install_bridge(package)
            self.assertNotIn(helper.MARKER,page.read_text(encoding='utf-8'))

    def test_unsupported_versions_are_not_modified(self):
        with tempfile.TemporaryDirectory(prefix='soft-voice-bubble-test-') as work:
            package=Path(work)
            (package/'web').mkdir(parents=True)
            (package/'package.json').write_text(json.dumps({'version':'99.0.0'}))
            page=package/'web/pet-app.js'
            page.write_text('page without the hooks',encoding='utf-8')
            with self.assertRaises(ValueError):helper.install_bridge(package)
            self.assertEqual(page.read_text(encoding='utf-8'),'page without the hooks')
            self.assertFalse((package/'web/soft-voice-bubble-sync.js').exists())

    def test_pet_release_that_already_ships_the_hooks_needs_no_patch(self):
        # Coopanion 0.2.1 ships cortico-world-desktop-pet 0.2.0 with the hooks
        # and the client already in place; the installer must not refuse it.
        with tempfile.TemporaryDirectory(prefix='soft-voice-bubble-test-') as work:
            package=Path(work)/'pet'
            (package/'web').mkdir(parents=True)
            (package/'package.json').write_text(json.dumps({'version':'0.2.0'}))
            page=package/'web/pet-app.js'
            page.write_text('\n'.join(after for _before,after in helper.HOOKS),encoding='utf-8')
            helper.install_bridge(package)
            self.assertIn(helper.MARKER,page.read_text(encoding='utf-8'))
            self.assertEqual(json.loads((package/'package.json').read_text())['version'],'0.2.0')
            self.assertEqual((package/'web/soft-voice-bubble-sync.js').read_bytes(),
                             (Path(__file__).resolve().parents[1]/'world/src/bubble-client.js').read_bytes())

if __name__=='__main__':unittest.main()
