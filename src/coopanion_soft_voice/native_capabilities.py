"""Reject a layout request when the loaded native library cannot implement it."""
import ctypes as C


def require_text_stream(dll):
    fn = getattr(dll, 'qt_text_embedding_stream_version', None)
    if fn is None:
        raise RuntimeError('Native library lacks text-row streaming; rebuild it or disable streamTextEmbedding')
    fn.argtypes = []
    fn.restype = C.c_int
    if fn() != 1:
        raise RuntimeError('Unsupported native text-row streaming version')
