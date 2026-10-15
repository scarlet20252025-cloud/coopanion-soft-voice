import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from coopanion_soft_voice import cli

class WorkerDiagnosticTests(unittest.TestCase):
    def test_initialization_failure_records_category_without_chat_or_trace(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(cli,'load',side_effect=RuntimeError('PRIVATE USER ERROR')),patch.object(sys,'stdout',io.StringIO()),patch.object(sys,'stderr',io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'PRIVATE USER ERROR'):cli.worker(Path(folder),mode='igpu')
            file=Path(folder)/'cache/worker-status.json';text=file.read_text(encoding='utf-8');status=json.loads(text)
            self.assertEqual(status['type'],'error');self.assertEqual(status['stage'],'initialization')
            self.assertEqual(status['errorKind'],'RuntimeError');self.assertNotIn('PRIVATE USER ERROR',text);self.assertNotIn('trace',status)
