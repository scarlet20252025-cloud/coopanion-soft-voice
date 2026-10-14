"""Losslessly remove analysis-only tensors from pinned GGUF v3 weights."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def integer(f, fmt):
    return struct.unpack('<'+fmt, f.read(struct.calcsize('<'+fmt)))[0]


def string(f):
    return f.read(integer(f, 'Q')).decode('utf-8')


def skip(f, kind):
    sizes = {0:1, 1:1, 2:2, 3:2, 4:4, 5:4, 6:4, 7:1, 10:8, 11:8, 12:8}
    if kind in sizes:
        f.seek(sizes[kind], 1)
    elif kind == 8:
        f.seek(integer(f, 'Q'), 1)
    elif kind == 9:
        element, count = integer(f, 'I'), integer(f, 'Q')
        if element in sizes: f.seek(sizes[element]*count, 1)
        else:
            for _ in range(count): skip(f, element)
    else:
        raise ValueError('Unknown GGUF metadata type')


def inspect(path):
    with Path(path).open('rb') as f:
        if f.read(4) != b'GGUF' or integer(f, 'I') != 3:
            raise ValueError('Expected GGUF v3')
        count, fields = integer(f, 'Q'), integer(f, 'Q')
        alignment = 32
        for _ in range(fields):
            key, kind = string(f), integer(f, 'I')
            if key == 'general.alignment':
                if kind != 4: raise ValueError('Invalid alignment type')
                alignment = integer(f, 'I')
            else: skip(f, kind)
        meta_end = f.tell()
        tensors = []
        for _ in range(count):
            start = f.tell(); name = string(f)
            dimensions = integer(f, 'I'); f.seek(8*dimensions+4, 1)
            offset = integer(f, 'Q'); end = f.tell()
            f.seek(start); descriptor = f.read(end-start)
            tensors.append(dict(name=name, offset=offset, descriptor=descriptor))
        data = (f.tell()+alignment-1)//alignment*alignment
        f.seek(24); metadata = f.read(meta_end-24)
    ordered = sorted(tensors, key=lambda x: x['offset'])
    for i, t in enumerate(ordered):
        end = ordered[i+1]['offset'] if i+1 < len(ordered) else Path(path).stat().st_size-data
        t['length'] = end-t['offset']
        if t['length'] <= 0: raise ValueError('Invalid tensor span')
    return metadata, fields, alignment, data, tensors


def strip(source, target, excluded):
    metadata, fields, alignment, data, tensors = inspect(source)
    keep = [t for t in tensors if not t['name'].startswith(excluded)]
    if not keep or len(keep) == len(tensors): raise ValueError('Expected analysis tensors not found')
    # Preserve tensor bytes, dtype, tokenizer and all metadata; only repack offsets.
    with Path(source).open('rb') as src, Path(target).open('xb') as dst:
        dst.write(struct.pack('<4sIQQ', b'GGUF', 3, len(keep), fields)); dst.write(metadata)
        offset = 0
        for t in keep:
            dst.write(t['descriptor'][:-8]+struct.pack('<Q', offset))
            offset += (t['length']+alignment-1)//alignment*alignment
        dst.write(b'\0' * ((-dst.tell()) % alignment))
        for t in keep:
            src.seek(data+t['offset']); remaining = t['length']
            while remaining:
                chunk = src.read(min(1024*1024, remaining))
                if not chunk: raise ValueError('Truncated input')
                dst.write(chunk); remaining -= len(chunk)
            dst.write(b'\0' * ((-t['length']) % alignment))
    return dict(before=Path(source).stat().st_size, after=Path(target).stat().st_size,
                removed=[t['name'] for t in tensors if t not in keep])


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*1024*1024), b''): h.update(chunk)
    return h.hexdigest()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('--output'); p.add_argument('--exclude')
    a = p.parse_args()
    if a.output:
        if not a.exclude: p.error('--exclude required')
        print(json.dumps(strip(a.source, a.output, tuple(a.exclude.split(','))), indent=2))
    else:
        _, _, _, _, tensors = inspect(a.source)
        groups = {}
        for t in tensors:
            prefix = t['name'].split('.')[0]
            groups[prefix] = groups.get(prefix, 0)+t['length']
        print(json.dumps(groups, indent=2))
