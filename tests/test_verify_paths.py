import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify_paths',ROOT/'scripts/verify_deployment.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)

class VerifyPathTests(unittest.TestCase):
    def test_runtime_file_is_rejected_before_loading_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);file=root/'native-runtime.json';file.write_text('{}')
            with self.assertRaisesRegex(ValueError,'runtime.*DIRECTORY'):verifier.verify(file,root/'output')

    def test_output_file_is_rejected_with_directory_explanation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);file=root/'deployment-check.json';file.write_text('{}')
            with self.assertRaisesRegex(ValueError,'output.*DIRECTORY'):verifier.verify(root,file)
