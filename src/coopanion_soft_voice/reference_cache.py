"""Bounded, versioned reference features; never deserialize executable objects."""
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path


def cache_path(runtime, config, reference):
    identity = [config['dllSha256'], config['model'], config['codec'],
                hashlib.sha256(Path(reference).read_bytes()).hexdigest(), 'reference-v1']
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return Path(runtime) / 'reference-cache' / (key + '.json')


def validate(payload):
    emb, codes, frames = payload['embedding'], payload['codes'], payload['frames']
    if (type(frames) is not int or not 1 <= frames <= 187 or
            len(emb) != 1024 or len(codes) != 16 * frames or
            any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 3.4e38 for x in emb) or
            any(type(x) is not int or not 0 <= x < 2048 for x in codes)):
        raise ValueError('Invalid reference features')
    return emb, codes, frames


def read(path):
    try:
        if path.stat().st_size > 100_000:
            return None
        doc = json.loads(path.read_text(encoding='utf-8'))
        raw = doc['payload']
        if hashlib.sha256(raw.encode()).hexdigest() != doc['sha256']:
            return None
        return validate(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None


def write(path, embedding, codes, frames):
    payload = dict(embedding=embedding, codes=codes, frames=frames)
    validate(payload)
    raw = json.dumps(payload, separators=(',', ':'), allow_nan=False)
    doc = json.dumps(dict(payload=raw, sha256=hashlib.sha256(raw.encode()).hexdigest()))
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as f:
            name = f.name
            f.write(doc)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
