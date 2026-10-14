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


def settings(runtime, *, cached_verification=False):
    config = json.loads((Path(runtime)/'native-runtime.json').read_text(encoding='utf-8'))
    speech_only = config.get('speechOnly')
    if speech_only and (speech_only.get('format') != 1 or speech_only.get('sourceHashes') != MODEL_HASHES):
        raise ValueError('Unsupported speech-only model provenance')
    for key in ('dll', 'model', 'codec'):
        path = Path(config[key]).resolve()
        if not path.is_file():
            raise ValueError('Missing native runtime file: ' + key)
        expected = (speech_only['hashes'][key] if speech_only else MODEL_HASHES[key]) if key != 'dll' else config['dllSha256']
        from .integrity_cache import verify
        verify(path, expected, Path(runtime)/'integrity-cache' if cached_verification and key != 'dll' else None)
        config[key] = str(path)
    context = config.get('kvContext', 4096)
    if type(context) is not int or context < 1024 or context > 4096 or context % 256:
        raise ValueError('kvContext must be a multiple of 256 between 1024 and 4096')
    config['kvContext'] = context
    if type(config.get('compactGraphs', False)) is not bool:
        raise ValueError('compactGraphs must be boolean')
    reference()
    config['deviceIndex'] = integrated_device(config['deviceName'])
    return config


class NativeEngine:
    sample_rate = 24000

    def __init__(self, runtime, voice_pack=None, *, use_reference_cache=True, buffer_mode='adaptive', on_stage=None):
        started = time.perf_counter()
        self.startup_timings = {}
        self.ctx = None; self.voice = Voice(); self.dirs = []
        self.cached_arrays = None
        if buffer_mode not in ('fixed', 'adaptive'): raise ValueError('Unknown startup buffer mode')
        self.buffer_mode = buffer_mode
        self.reference_path = reference()
        self.reference_text = REFERENCE_TEXT
        if voice_pack:
            from .voice_pack import load
            self.reference_path, pack = load(voice_pack)
            self.reference_text = pack['referenceText']
        report = on_stage or (lambda name, detail: None)
        report('validate_model','正在校验模型文件并检查核显')
        config = settings(runtime, cached_verification=True)
        self.startup_timings['validationMs'] = round((time.perf_counter()-started)*1000)
        class MemoryStatus(C.Structure):
            _fields_ = [('length', C.c_uint32), ('load', C.c_uint32)] + [
                (n, C.c_uint64) for n in ('total', 'available', 'pageTotal', 'pageAvailable',
                                         'virtualTotal', 'virtualAvailable', 'extended')]
        memory = MemoryStatus(); memory.length = C.sizeof(memory)
        from .memory_policy import loading_requirement
        minimum = loading_requirement(config)
        report('check_memory','正在检查加载所需的系统内存')
        measured = C.windll.kernel32.GlobalMemoryStatusEx(C.byref(memory))
        self.startup_timings['availableBeforeLoadGiB'] = round(memory.available/1024**3, 4) if measured else None
        if not measured or memory.available < minimum*1024**3:
            raise RuntimeError(f'Native voice needs at least {minimum:g} GiB free RAM before loading; keeping text only')
        os.environ['GGML_BACKEND'] = 'Vulkan0'
        os.environ['GGML_VK_VISIBLE_DEVICES'] = str(config['deviceIndex'])
        os.environ['QWEN_CPU_THREADS'] = '4'
        os.environ['QWEN_TTS_KV_CONTEXT'] = str(config['kvContext'])
        if config.get('compactGraphs', False): os.environ['QWEN_TTS_COMPACT_GRAPHS'] = '1'
        else: os.environ.pop('QWEN_TTS_COMPACT_GRAPHS', None)
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
            loading = time.perf_counter()
            report('load_model','正在加载模型权重与推理缓存')
            self.ctx = self.dll.qt_init(C.byref(init))
            self.startup_timings['modelInitMs'] = round((time.perf_counter()-loading)*1000)
            if not self.ctx:
                raise RuntimeError(self.dll.qt_last_error().decode())
            report('prepare_voice','正在准备已确认的音色特征')
            from . import reference_cache
            cache = reference_cache.cache_path(runtime, config, self.reference_path)
            fixed = config.get('speechOnly')
            if fixed:
                if not use_reference_cache:
                    raise ValueError('Speech-only runtime requires pre-extracted reference features')
                if hashlib.sha256(self.reference_path.read_bytes()).hexdigest() != fixed['referenceSha256']:
                    raise ValueError('Speech-only runtime is bound to its reference voice; build a new profile for this voice or restore the full runtime')
                feature_path = Path(runtime) / 'voice-features.json'
                if hashlib.sha256(feature_path.read_bytes()).hexdigest() != fixed['featuresSha256']:
                    raise ValueError('Speech-only reference features checksum mismatch; rebuild this profile')
                features = reference_cache.read(feature_path)
                if features is None:
                    raise ValueError('Speech-only reference features invalid; rebuild this profile')
            else:
                features = reference_cache.read(cache) if use_reference_cache else None
            self.reference_cache_hit = features is not None
            if features is not None:
                emb, codes, frames = features
                # Python owns these arrays. Never pass them to the C malloc/free API.
                self.cached_arrays = ((C.c_float * len(emb))(*emb), (C.c_int32 * len(codes))(*codes))
                self.voice = Voice(self.cached_arrays[0], len(emb), self.cached_arrays[1], frames, 16)
            else:
                import soundfile as sf
                ref, rate = sf.read(self.reference_path, dtype='float32')
                if rate != 24000 or ref.ndim != 1:
                    raise ValueError('Invalid reference format')
                if self.dll.qt_extract_voice_ref(self.ctx, ref.ctypes.data_as(F32), len(ref), C.byref(self.voice)):
                    raise RuntimeError(self.dll.qt_last_error().decode())
                if use_reference_cache:
                    try:
                        reference_cache.write(cache, list(self.voice.ref_spk_emb[:self.voice.ref_spk_dim]),
                                              list(self.voice.ref_codes[:16*self.voice.ref_T]), self.voice.ref_T)
                    except (OSError, ValueError):
                        pass  # Read-only cache must not break speech.
                    # Extraction-only encoder weights and scratch allocations are lazy in upstream.
                    # Recreate the context once to release them; the malloc-owned reference survives.
                    self.dll.qt_free(self.ctx); self.ctx = None
                    self.ctx = self.dll.qt_init(C.byref(init))
                    if not self.ctx:
                        raise RuntimeError(self.dll.qt_last_error().decode())
            self.device_name = config['deviceName']
            self.startup_timings['totalMs'] = round((time.perf_counter()-started)*1000)
        except BaseException:
            self.close(); raise

    def synthesize_stream(self, text, key, receive, on_complete=None):
        import numpy as np
        if not self.ctx:
            raise RuntimeError('Native engine closed')
        if not text.strip() or len(text) > 60:
            raise ValueError('Native synthesis requires 1-60 characters per piece')
        p = Params(); self.dll.qt_tts_default_params(C.byref(p))
        p.text = text.encode(); p.lang = b'Chinese'; p.ref_text = self.reference_text.encode()
        p.ref_spk_emb = self.voice.ref_spk_emb; p.ref_spk_dim = self.voice.ref_spk_dim
        p.ref_codes = self.voice.ref_codes; p.ref_T = self.voice.ref_T
        p.seed = 44; p.max_new_tokens = 360
        p.temperature = .9; p.top_k = 50; p.top_p = 1; p.repetition_penalty = 1.05
        p.subtalker_temperature = .9; p.subtalker_top_k = 50; p.subtalker_top_p = 1
        pending = []; count = 0; total_samples = 0; opened = False; errors = []; started = time.perf_counter()
        from .start_buffer import StartBuffer
        gate = StartBuffer(fixed=getattr(self, 'buffer_mode', 'adaptive') == 'fixed')
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
                    if gate.feed(n, time.perf_counter()):
                        self.last_start_buffer = {'chunks':gate.chunks,'bufferSeconds':count/24000,
                                                  'targetSeconds':gate.target_seconds,'maxGap':gate.max_gap}
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
        if getattr(self, 'dll', None) and not self.cached_arrays:
            self.dll.qt_voice_ref_free(C.byref(self.voice))
        if self.ctx:
            self.dll.qt_free(self.ctx); self.ctx = None
        self.voice = Voice(); self.cached_arrays = None
        for folder in self.dirs: folder.close()
        self.dirs.clear()
