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


def require_adaptive_kv(dll):
    fn = getattr(dll, 'qt_adaptive_kv_version', None)
    state = getattr(dll, 'qt_adaptive_kv_state', None)
    if fn is None or state is None:
        raise RuntimeError('Native library lacks progressive KV storage; rebuild it or disable adaptiveKv')
    fn.argtypes = []
    fn.restype = C.c_int
    if fn() != 1:
        raise RuntimeError('Unsupported native progressive KV version')
    state.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_uint64)]
    state.restype = C.c_int
