"""Experimental full-ICL Q8 engine restricted to an explicitly named integrated GPU."""
import ctypes as C
import hashlib
import json
import os
import time
from pathlib import Path
from .native_abi import Init, Params, Voice, Audio, Chunk, Cancel, F32
from .config import reference, REFERENCE_TEXT

MODEL_HASHES = {
    'model': 'd54dbaf10591421fa764ed630d764efa717ae40cd959bd48c66d4eb1af226426',
    'codec': '1883beeed99348fc35e23dd225e9082f93f6f8c109330a33d935baa8acdbfd94',
}


def integrated_device(name):
    """Enumerate without creating a GPU device; never silently select a discrete GPU."""
    class Create(C.Structure):
        _fields_ = [('sType', C.c_uint32), ('next', C.c_void_p), ('flags', C.c_uint32),
                    ('app', C.c_void_p), ('nl', C.c_uint32), ('layers', C.c_void_p),
                    ('ne', C.c_uint32), ('extensions', C.c_void_p)]
    v = C.WinDLL('vulkan-1.dll')
    v.vkCreateInstance.argtypes = [C.POINTER(Create), C.c_void_p, C.POINTER(C.c_void_p)]
    v.vkCreateInstance.restype = C.c_int
    v.vkEnumeratePhysicalDevices.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.c_void_p]
    v.vkGetPhysicalDeviceProperties.argtypes = [C.c_void_p, C.c_void_p]
    v.vkDestroyInstance.argtypes = [C.c_void_p, C.c_void_p]
    instance = C.c_void_p(); create = Create(); create.sType = 1
    if v.vkCreateInstance(C.byref(create), None, C.byref(instance)):
        raise RuntimeError('Vulkan instance unavailable')
    try:
        count = C.c_uint32()
        if v.vkEnumeratePhysicalDevices(instance, C.byref(count), None):
            raise RuntimeError('Cannot enumerate Vulkan devices')
        devices = (C.c_void_p * count.value)()
        if v.vkEnumeratePhysicalDevices(instance, C.byref(count), devices):
            raise RuntimeError('Vulkan device list changed; retry')
        matches = []
        for i, device in enumerate(devices):
            buf = C.create_string_buffer(4096)
            v.vkGetPhysicalDeviceProperties(device, buf)
            kind = int.from_bytes(buf.raw[16:20], 'little')
            actual = buf.raw[20:276].split(b'\0')[0].decode('utf-8')
            if kind == 1 and actual == name:
                matches.append(i)
        if len(matches) != 1:
            raise RuntimeError('Expected exactly one matching integrated GPU; no discrete GPU fallback')
        return matches[0]
    finally:
        v.vkDestroyInstance(instance, None)


def settings(runtime):
    config = json.loads((Path(runtime)/'native-runtime.json').read_text(encoding='utf-8'))
    for key in ('dll', 'model', 'codec'):
        path = Path(config[key]).resolve()
        if not path.is_file():
            raise ValueError('Missing native runtime file: ' + key)
        digest = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(8*1024*1024), b''):
                digest.update(block)
        expected = MODEL_HASHES[key] if key != 'dll' else config['dllSha256']
        if digest.hexdigest() != expected:
            raise ValueError('Native runtime checksum mismatch: ' + key)
        config[key] = str(path)
    reference()
    config['deviceIndex'] = integrated_device(config['deviceName'])
    return config


class NativeEngine:
    sample_rate = 24000

    def __init__(self, runtime):
        self.ctx = None; self.voice = Voice(); self.dirs = []
        config = settings(runtime)
        class MemoryStatus(C.Structure):
            _fields_ = [('length', C.c_uint32), ('load', C.c_uint32)] + [
                (n, C.c_uint64) for n in ('total', 'available', 'pageTotal', 'pageAvailable',
                                         'virtualTotal', 'virtualAvailable', 'extended')]
        memory = MemoryStatus(); memory.length = C.sizeof(memory)
        if not C.windll.kernel32.GlobalMemoryStatusEx(C.byref(memory)) or memory.available < 4*1024**3:
            raise RuntimeError('Native voice needs at least 4 GiB free RAM before loading; keeping text only')
        os.environ['GGML_BACKEND'] = 'Vulkan0'
        os.environ['GGML_VK_VISIBLE_DEVICES'] = str(config['deviceIndex'])
        os.environ['QWEN_CPU_THREADS'] = '4'
        kernel = C.windll.kernel32
        kernel.GetCurrentProcess.restype = C.c_void_p
        kernel.SetPriorityClass.argtypes = [C.c_void_p, C.c_ulong]
        if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
            raise RuntimeError('Cannot lower worker priority')
        try:
            for folder in [str(Path(config['dll']).parent)] + config['dllDirectories']:
                self.dirs.append(os.add_dll_directory(folder))
            self.dll = C.CDLL(config['dll'])
            signatures = {
                'qt_version': ([], C.c_char_p), 'qt_last_error': ([], C.c_char_p),
                'qt_init_default_params': ([C.POINTER(Init)], None),
                'qt_init': ([C.POINTER(Init)], C.c_void_p), 'qt_free': ([C.c_void_p], None),
                'qt_tts_default_params': ([C.POINTER(Params)], None),
                'qt_extract_voice_ref': ([C.c_void_p, F32, C.c_int, C.POINTER(Voice)], C.c_int),
                'qt_voice_ref_free': ([C.POINTER(Voice)], None),
                'qt_synthesize': ([C.c_void_p, C.POINTER(Params), C.POINTER(Audio)], C.c_int),
                'qt_audio_free': ([C.POINTER(Audio)], None),
            }
            for name, (args, result) in signatures.items():
                fn = getattr(self.dll, name); fn.argtypes = args; fn.restype = result
            if not self.dll.qt_version().decode().startswith('51512f1 '):
                raise RuntimeError('Unverified native engine revision')
            init = Init(); self.dll.qt_init_default_params(C.byref(init))
            if init.abi_version != 5:
                raise RuntimeError('Unsupported native ABI')
            init.talker_path = config['model'].encode(); init.codec_path = config['codec'].encode()
            init.max_batch = 1; init.use_fa = False
            self.ctx = self.dll.qt_init(C.byref(init))
            if not self.ctx:
                raise RuntimeError(self.dll.qt_last_error().decode())
            import soundfile as sf
            ref, rate = sf.read(reference(), dtype='float32')
            if rate != 24000 or ref.ndim != 1:
                raise ValueError('Invalid reference format')
            if self.dll.qt_extract_voice_ref(self.ctx, ref.ctypes.data_as(F32), len(ref), C.byref(self.voice)):
                raise RuntimeError(self.dll.qt_last_error().decode())
            self.device_name = config['deviceName']
        except BaseException:
            self.close(); raise

    def synthesize_stream(self, text, key, receive, on_complete=None):
        import numpy as np
        if not self.ctx:
            raise RuntimeError('Native engine closed')
        if not text.strip() or len(text) > 60:
            raise ValueError('Native synthesis requires 1-60 characters per piece')
        p = Params(); self.dll.qt_tts_default_params(C.byref(p))
        p.text = text.encode(); p.lang = b'Chinese'; p.ref_text = REFERENCE_TEXT.encode()
        p.ref_spk_emb = self.voice.ref_spk_emb; p.ref_spk_dim = self.voice.ref_spk_dim
        p.ref_codes = self.voice.ref_codes; p.ref_T = self.voice.ref_T
        p.seed = 44; p.max_new_tokens = 360
        p.temperature = .9; p.top_k = 50; p.top_p = 1; p.repetition_penalty = 1.05
        p.subtalker_temperature = .9; p.subtalker_top_k = 50; p.subtalker_top_p = 1
        pending = []; count = 0; total_samples = 0; opened = False; errors = []; started = time.perf_counter()
        @Cancel
        def cancel(user): return time.perf_counter()-started > 60
        @Chunk
        def chunk(samples, n, user):
            nonlocal count, total_samples, opened
            try:
                data = np.ctypeslib.as_array(samples, shape=(n,)).copy()
                if not np.isfinite(data).all(): raise ValueError('Nonfinite audio')
                total_samples += n
                if opened:
                    receive(data, 24000)
                else:
                    pending.append(data); count += n
                    if count >= 28800:
                        receive(np.concatenate(pending), 24000); pending.clear(); opened = True
                return True
            except Exception as exc:
                errors.append(exc); return False
        p.cancel = cancel; p.on_chunk = chunk; out = Audio()
        try:
            status = self.dll.qt_synthesize(self.ctx, C.byref(p), C.byref(out))
        finally:
            self.dll.qt_audio_free(C.byref(out))
        if status or errors:
            raise RuntimeError(str(errors[0]) if errors else self.dll.qt_last_error().decode())
        # The native API reports success even when generation hits its frame cap.
        # Do not label a potentially truncated utterance as complete.
        if total_samples >= p.max_new_tokens * 1920:
            raise RuntimeError('Speech reached the generation limit; output may be incomplete')
        if not total_samples:
            raise RuntimeError('Native engine returned no audio')
        if on_complete: on_complete()
        if pending: receive(np.concatenate(pending), 24000)

    def close(self):
        if self.ctx:
            self.dll.qt_voice_ref_free(C.byref(self.voice))
            self.dll.qt_free(self.ctx); self.ctx = None
        for folder in self.dirs: folder.close()
        self.dirs.clear()
