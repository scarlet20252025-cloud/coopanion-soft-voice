"""Read Windows GPU process counters, without confusing whole-card usage with TTS.

PDH English counter names work on localized Windows. Missing counters are unknown,
never zero. Dedicated and shared bytes are reported separately across adapters.
"""
import ctypes as C
import os
import re
import sys


class CounterValue(C.Structure):
    _fields_ = [('status', C.c_uint32), ('value', C.c_int64)]


class CounterItem(C.Structure):
    _fields_ = [('name', C.c_wchar_p), ('value', CounterValue)]


def process_total(items, pid):
    """None means no valid sample; zero is a measured value, not a fallback."""
    prefix = re.compile(r'^pid_' + str(pid) + r'_luid_', re.I)
    values = [value for name, status, value in items
              if name and prefix.match(name) and status in (0, 1) and value >= 0]
    return sum(values) if values else None


class GpuMemory:
    def __init__(self, pid=None):
        self.pid = os.getpid() if pid is None else int(pid)
        self.query = C.c_void_p()
        self.counters = {}
        self.error = None
        if sys.platform != 'win32':
            self.error = 'Windows GPU process counters unavailable'
            return
        try:
            self.api = C.WinDLL('pdh.dll')
            self.api.PdhOpenQueryW.argtypes = [C.c_wchar_p, C.c_size_t, C.POINTER(C.c_void_p)]
            self.api.PdhAddEnglishCounterW.argtypes = [C.c_void_p, C.c_wchar_p, C.c_size_t, C.POINTER(C.c_void_p)]
            self.api.PdhCollectQueryData.argtypes = [C.c_void_p]
            self.api.PdhGetFormattedCounterArrayW.argtypes = [C.c_void_p, C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.c_void_p]
            self.api.PdhCloseQuery.argtypes = [C.c_void_p]
            for name in ('PdhOpenQueryW', 'PdhAddEnglishCounterW', 'PdhCollectQueryData', 'PdhGetFormattedCounterArrayW', 'PdhCloseQuery'):
                getattr(self.api, name).restype = C.c_uint32
            code = self.api.PdhOpenQueryW(None, 0, C.byref(self.query))
            if code:
                raise OSError(f'PdhOpenQueryW: 0x{code:08x}')
            for label, counter in (('dedicatedMiB', 'Dedicated Usage'), ('sharedMiB', 'Shared Usage')):
                handle = C.c_void_p()
                code = self.api.PdhAddEnglishCounterW(self.query, '\\GPU Process Memory(*)\\' + counter, 0, C.byref(handle))
                if code:
                    raise OSError(f'PdhAddEnglishCounterW: 0x{code:08x}')
                self.counters[label] = handle
        except (OSError, AttributeError) as exc:
            self.error = str(exc)
            self.close()

    def _read(self, handle):
        for _ in range(3):  # Instances can change between the size and data calls.
            size, count = C.c_uint32(), C.c_uint32()
            code = self.api.PdhGetFormattedCounterArrayW(handle, 0x400, C.byref(size), C.byref(count), None)
            if code not in (0, 0x800007d2) or not 0 < size.value <= 16 * 1024**2:
                return None
            buf = C.create_string_buffer(size.value)
            code = self.api.PdhGetFormattedCounterArrayW(handle, 0x400, C.byref(size), C.byref(count), buf)
            if code == 0x800007d2:
                continue
            if code or count.value * C.sizeof(CounterItem) > len(buf):
                return None
            items = C.cast(buf, C.POINTER(CounterItem))
            return process_total(((items[i].name, items[i].value.status, items[i].value.value)
                                  for i in range(count.value)), self.pid)
        return None

    def snapshot(self):
        result = {'source': 'Windows GPU Process Memory', 'scope': 'process-all-adapters',
                  'dedicatedMiB': None, 'sharedMiB': None}
        if self.error or not self.query:
            return {**result, 'error': self.error or 'Counter query closed'}
        code = self.api.PdhCollectQueryData(self.query)
        if code:
            return {**result, 'error': f'PdhCollectQueryData: 0x{code:08x}'}
        for label, handle in self.counters.items():
            value = self._read(handle)
            result[label] = round(value / 1024**2, 3) if value is not None else None
        return result

    def close(self):
        if self.query:
            self.api.PdhCloseQuery(self.query)
            self.query = C.c_void_p()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
