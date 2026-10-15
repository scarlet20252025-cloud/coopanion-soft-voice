import unittest
from types import SimpleNamespace
from coopanion_soft_voice.native_capabilities import require_text_stream, require_adaptive_kv

class NativeCapabilityTests(unittest.TestCase):
    def test_old_dll_cannot_silently_accept_smaller_layout(self):
        with self.assertRaisesRegex(RuntimeError, 'rebuild'):
            require_text_stream(SimpleNamespace())

    def test_unknown_implementation_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            require_text_stream(SimpleNamespace(qt_text_embedding_stream_version=lambda:2))

    def test_known_implementation_is_accepted(self):
        require_text_stream(SimpleNamespace(qt_text_embedding_stream_version=lambda:1))

    def test_progressive_cache_requires_both_capability_and_state_reporting(self):
        with self.assertRaisesRegex(RuntimeError, 'rebuild'):
            require_adaptive_kv(SimpleNamespace(qt_adaptive_kv_version=lambda:1))
        with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
            require_adaptive_kv(SimpleNamespace(qt_adaptive_kv_version=lambda:2, qt_adaptive_kv_state=lambda:1))
        require_adaptive_kv(SimpleNamespace(qt_adaptive_kv_version=lambda:1, qt_adaptive_kv_state=lambda:1))
