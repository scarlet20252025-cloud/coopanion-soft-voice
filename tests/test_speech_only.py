import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('strip_weights', Path(__file__).parents[1]/'scripts/strip_speech_weights.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def string(value):
    data = value.encode(); return struct.pack('<Q', len(data))+data


class SpeechOnlyTests(unittest.TestCase):
    def test_repack_preserves_metadata_and_retained_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d)/'source.gguf', Path(d)/'output.gguf'
            metadata = string('general.name')+struct.pack('<I',8)+string('test')
            header = struct.pack('<4sIQQ', b'GGUF',3,3,1)+metadata
            for i, name in enumerate(['talker.keep','spk_enc.remove','code_pred.keep']):
                header += string(name)+struct.pack('<IQIQ',1,8,0,32*i)
            header += b'\0' * ((-len(header)) % 32)
            src.write_bytes(header+b'A'*32+b'B'*32+b'C'*32)
            result = module.strip(src,dst,('spk_enc.',))
            meta, _, _, offset, tensors = module.inspect(dst)
            self.assertEqual(meta, metadata)
            self.assertEqual([t['name'] for t in tensors],['talker.keep','code_pred.keep'])
            self.assertEqual(dst.read_bytes()[offset:], b'A'*32+b'C'*32)
            self.assertEqual(result['removed'],['spk_enc.remove'])
            with self.assertRaises(FileExistsError): module.strip(src,dst,('spk_enc.',))

    def test_invalid_format_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad'; path.write_bytes(b'nope')
            with self.assertRaises(ValueError): module.inspect(path)


if __name__ == '__main__': unittest.main()
