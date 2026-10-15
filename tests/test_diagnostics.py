import hashlib,importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from coopanion_soft_voice import diagnostics as d

from coopanion_soft_voice import issue_reporting as reporter

class DiagnosticsTests(unittest.TestCase):
    def fixture(self,root):
        (root/'cache').mkdir()
        (root/'native-runtime.json').write_text(json.dumps({'deviceName':'NVIDIA','deviceType':'discrete','kvContext':1024,'apiKey':'secret-not-collectable','model':'C:/Users/Alice/Private/model.gguf','speechOnly':{'format':1}}))
        (root/'cache/last-stream-metrics.json').write_text(json.dumps({'seconds':5,'totalSynthesisMs':2000,'realTimeFactor':.4,'underrunMs':0,'deviceUnderflows':0,'effectivePlaybackMode':'stream','text':'PRIVATE CHAT','audioFile':'C:/Users/Alice/private.wav','nativeSettings':{'memoryPolicy':'device-local','secret':'DO NOT COPY'}}))
        (root/'cache/worker-status.json').write_text(json.dumps({'type':'ready','device':'NVIDIA','processMemory':{'privateMiB':2048,'text':'PRIVATE CHAT'},'trace':'account-secret'}))
        log=root/'worker.log';log.write_text('PRIVATE CHAT\n[Perf] Total 2000 ms (audio 5 s, RTF 0.4); PRIVATE CHAT\n',encoding='utf-8')
        return log

    def collect(self,root,output):
        with patch.object(d,'static_info',return_value={'cpu':'test'}),patch.object(d,'vulkan_info',return_value=[]),patch.object(d,'owned_workers',return_value=[]),patch.object(d,'nvidia_sample',return_value=[]),patch.object(d,'system_memory',return_value={'availableGiB':4}):
            return d.collect(root,output)

    def test_numeric_whitelist_excludes_chat_paths_and_unknown_config_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);archive=self.collect(root,root/'out')
            report,files=reporter.read_package(archive)
            contents=b'\n'.join(files.values()).decode('utf-8')
            for private in ('PRIVATE CHAT','secret-not-collectable','DO NOT COPY','account-secret','Alice','private.wav'):self.assertNotIn(private,contents)
            self.assertEqual(report['summary']['realTimeFactor'],.4)
            self.assertEqual(report['samples'][0]['recentPlayback']['nativeSettings'],{'memoryPolicy':'device-local'})
            self.assertIn('2000',files['perf.log'].decode())

    def test_monitor_bounds_and_output_directory_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);file=root/'file';file.touch()
            for seconds,interval in [(-1,2),(301,2),(0,0),(0,31),(True,2)]:
                with self.assertRaises(ValueError):d.collect(root,root/'out',seconds=seconds,interval=interval)
            with self.assertRaisesRegex(ValueError,'output.*directory'):d.collect(root,file)

    def test_missing_and_corrupt_metrics_are_unknown_not_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'cache').mkdir();(root/'cache/last-stream-metrics.json').write_text('broken')
            archive=self.collect(root,root/'out');report,_=reporter.read_package(archive)
            self.assertIsNone(report['summary']['realTimeFactor']);self.assertIsNone(report['summary']['underrunMs'])

    def test_path_with_spaces_and_authorization_token_are_redacted(self):
        text='path="C:\\Users\\Alice\\Private Folder\\audio.wav"\nAuthorization: Bearer opaque-abcdef-token\nemail=alice@example.com\npassword: literal secret with spaces'
        masked=d.redact(text)
        for private in ('Alice','Private Folder','audio.wav','opaque-abcdef-token','alice@example.com','literal secret'):self.assertNotIn(private,masked)

    def test_draft_never_fetches_credentials_or_posts_without_submit(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(reporter,'credentials') as auth,patch.object(reporter.urllib.request,'urlopen') as http:
            root=Path(tmp);self.fixture(root);archive=self.collect(root,root/'out')
            result,fallback=reporter.run(archive)
            self.assertFalse(result['submitted']);auth.assert_not_called();http.assert_not_called()
            _,files=reporter.read_package(fallback)
            self.assertIn('analysis.md',files);self.assertIn('issue-draft.md',files)
            self.assertIn('perf.log',files);self.assertFalse(json.loads(files['submission.json'])['submitted'])

    def test_no_auth_or_network_error_returns_complete_fallback(self):
        for token in (None,'opaque-test-token'):
            with tempfile.TemporaryDirectory() as tmp,patch.object(reporter,'credentials',return_value=token),patch.object(reporter.urllib.request,'urlopen',side_effect=OSError('offline')):
                root=Path(tmp);self.fixture(root);archive=self.collect(root,root/'out')
                result,fallback=reporter.run(archive,submit=True)
                self.assertFalse(result['submitted']);self.assertTrue(fallback.is_file())
                self.assertNotIn('opaque-test-token',fallback.read_bytes().decode('latin-1'))

    def test_checksum_mismatch_is_rejected_before_reporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root);archive=self.collect(root,root/'out')
            with zipfile.ZipFile(archive) as z:files={name:z.read(name) for name in z.namelist()}
            files['perf.log']=b'changed';tampered=root/'tampered.zip'
            with zipfile.ZipFile(tampered,'w') as z:
                for name,data in files.items():z.writestr(name,data)
            with self.assertRaisesRegex(ValueError,'checksum'):reporter.read_package(tampered)
