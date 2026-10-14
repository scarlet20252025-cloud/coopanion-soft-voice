"""Process counters sampled at load, playback completion and sleep, never per audio frame."""
import ctypes as C
import sys

def snapshot():
    if sys.platform != 'win32':
        return None
    from .native_abi import Memory
    kernel = C.windll.kernel32
    kernel.GetCurrentProcess.restype = C.c_void_p
    api = C.windll.psapi.GetProcessMemoryInfo
    api.argtypes = [C.c_void_p, C.POINTER(Memory), C.c_ulong]
    counters = Memory(); counters.cb = C.sizeof(counters)
    if not api(kernel.GetCurrentProcess(), C.byref(counters), counters.cb):
        return None
    return {'privateMiB': round(counters.pagefile / 1024**2, 1),
            'residentMiB': round(counters.workingSet / 1024**2, 1),
            'peakResidentMiB': round(counters.peakWorkingSet / 1024**2, 1)}
