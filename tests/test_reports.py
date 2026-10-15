import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coopanion_soft_voice import diagnostics as d, issue_reporting as reporter
from coopanion_soft_voice.reports import Reports


class ReportLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=self.root/'runtime';self.runtime.mkdir()
        self.data=self.root/'data';self.data.mkdir();self.reports=Reports(self.runtime,self.data)
        for name,value in [('static_info',{'cpu':'test'}),('vulkan_info',[]),('owned_workers',[]),('nvidia_sample',[]),('system_memory',None)]:
            mock=patch.object(d,name,return_value=value);mock.start();self.addCleanup(mock.stop)

    def test_local_report_export_and_detail_never_request_credentials(self):
        with patch.object(reporter,'credentials') as auth:
            row=self.reports.collect()['report'];detail=self.reports.detail(row['id']);export=self.reports.export(row['id'])
        auth.assert_not_called();self.assertEqual(detail['report']['title'],'手动检查')
        archive=self.root/'export.zip';archive.write_bytes(base64.b64decode(export['base64']))
        _,files=reporter.read_package(archive)
        self.assertTrue({'diagnostics.json','perf.log','issue-draft.md','AI_PROMPT.txt'}<=set(files))
        self.assertFalse(row['submission']['submitted'])

    def test_automatic_cooldown_survives_reconstruction_and_limits_daily_reports(self):
        self.reports.collect(code='worker_error',automatic=True)
        restarted=Reports(self.runtime,self.data)
        self.assertTrue(restarted.collect(code='worker_error',automatic=True)['skipped'])
        restarted.collect(code='worker_exit',automatic=True);restarted.collect(code='slow_synthesis',automatic=True)
        self.assertTrue(restarted.collect(code='speech_timeout',automatic=True)['skipped'])
        self.assertEqual(len(restarted.list()['reports']),3)

    def test_submit_requires_authorization_and_offline_attempt_does_not_loop(self):
        row=self.reports.collect()['report']
        with self.assertRaisesRegex(ValueError,'requires'):self.reports.submit(row['id'])
        with patch.object(reporter,'credentials',return_value=None) as auth:
            result=self.reports.submit(row['id'],True,True)
            again=Reports(self.runtime,self.data).submit(row['id'],True,True)
        self.assertFalse(result['report']['submission']['submitted']);self.assertTrue(again['skipped']);auth.assert_called_once()
        self.assertIn('凭据',result['report']['submission']['reason'])
        self.assertTrue(self.reports.export(row['id'])['base64'])

    def test_report_id_and_redirects_cannot_read_another_file(self):
        for value in ('../secret','C:/private','a'*31,None):
            with self.assertRaises(ValueError):self.reports.detail(value)

    def test_retention_only_prunes_own_uuid_folders(self):
        unrelated=self.reports.root/'personal';unrelated.mkdir();(unrelated/'keep').touch()
        with patch('coopanion_soft_voice.reports.MAX_REPORTS',2):
            # Record listing default remains twenty, pruning uses the configured bound.
            for _ in range(3):self.reports.collect()
        self.assertEqual(len(self.reports.records()),2);self.assertTrue((unrelated/'keep').is_file())

    def test_duplicate_automatic_issue_returns_existing_link_without_posting(self):
        row=self.reports.collect()['report'];folder,record=self.reports.record(row['id'])
        archive=self.reports.archive(folder,record)
        _,files=reporter.read_package(archive);body=files['issue-draft.md'].decode('utf-8')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self):return json.dumps([{'number':7,'html_url':'https://github.com/'+reporter.REPO+'/issues/7','body':body}]).encode()
        with patch.object(reporter,'credentials',return_value='test'),patch.object(reporter.urllib.request,'urlopen',return_value=Response()) as http:
            result,_=reporter.run(archive,folder/'analysis.md',submit=True,skip_duplicate=True)
        self.assertTrue(result['submitted']);self.assertTrue(result['url'].endswith('/7'))
        http.assert_called_once();self.assertIsNone(http.call_args[0][0].data)
