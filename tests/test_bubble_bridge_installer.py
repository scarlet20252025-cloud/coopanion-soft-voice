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
            (package/'package.json').write_text(json.dumps({'version':'99.0.0'}))
            with self.assertRaises(ValueError):helper.install_bridge(package)

if __name__=='__main__':unittest.main()
