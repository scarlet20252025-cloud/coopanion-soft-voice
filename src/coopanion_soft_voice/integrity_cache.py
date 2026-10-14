"""Reuse a local verification receipt only while file identity and timestamps match."""
import hashlib
import json
import os
import tempfile
from pathlib import Path


def identity(path):
    s = path.stat()
    return [str(path.resolve()), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def verify(path, expected, cache_dir=None):
    before = identity(path)
    record = dict(identity=before, sha256=expected)
    receipt = None
    if cache_dir:
        receipt = Path(cache_dir) / (hashlib.sha256(str(path).encode()).hexdigest()+'.json')
        try:
            if receipt.stat().st_size < 8192 and json.loads(receipt.read_text('utf-8')) == record:
                return True
        except (OSError, ValueError):
            pass
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''): h.update(block)
    if h.hexdigest() != expected or identity(path) != before:
        raise ValueError('Native runtime checksum mismatch: '+path.name)
    if receipt:
        temporary = None
        try:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=receipt.parent, delete=False) as f:
                temporary = f.name; json.dump(record, f)
            os.replace(temporary, receipt)
        except OSError:
            pass
        finally:
            if temporary and os.path.exists(temporary): os.unlink(temporary)
    return False
