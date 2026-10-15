"""One World payload for npm, offline installation and GitHub updates."""
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

NAME = 'cortico-world-soft-voice'


def managed(name):
    p = PurePosixPath(name)
    return (name in ('package.json', 'README.md', 'LICENSE') or
            len(p.parts) > 1 and p.parts[0] in ('src', 'dist'))


def payload(source):
    """Developer tree projection; release builds compare this to actual npm pack."""
    source = Path(source).resolve()
    result = {}
    for f in source.rglob('*'):
        name = f.relative_to(source).as_posix()
        if (f.is_file() and managed(name) and not any(x.startswith('.') or x == '__pycache__' for x in f.relative_to(source).parts)
                and f.suffix != '.pyc'):
            if f.resolve() != f.absolute():
                raise ValueError('World package must not contain links')
            result[name] = f.read_bytes()
    meta = json.loads(result['package.json'])
    if meta.get('name') != NAME:
        raise ValueError('Unexpected World package identity')
    return result


def archive_payload(archive):
    result = {}
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 1500 or sum(m.size for m in members) > 32*1024**2:
            raise ValueError('World archive exceeds limits')
        for m in members:
            if m.isdir():
                continue
            p = PurePosixPath(m.name)
            if (not m.isfile() or p.is_absolute() or len(p.parts) < 2 or p.parts[0] != 'package'
                    or any(x in ('.', '..') for x in p.parts) or '\\' in m.name or ':' in m.name):
                raise ValueError('Unsafe npm package member')
            name = PurePosixPath(*p.parts[1:]).as_posix()
            if not managed(name) or name in result:
                raise ValueError('Unexpected npm package member')
            result[name] = tar.extractfile(m).read()
    if json.loads(result['package.json']).get('name') != NAME:
        raise ValueError('Unexpected World package identity')
    return result


def pack(source, output, archive=None):
    """Pack once, reuse exactly this TGZ for registry and both download packages."""
    source, output = Path(source).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if archive is None:
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm:
            raise RuntimeError('Release packaging requires npm, or --world-package with the already packed TGZ')
        done = subprocess.run([npm, 'pack', '--ignore-scripts', '--json', '--pack-destination', str(output)],
                              cwd=source, check=True, text=True, encoding='utf-8', capture_output=True)
        archive = output / json.loads(done.stdout)[0]['filename']
    archive = Path(archive).resolve()
    files = archive_payload(archive)
    if files != payload(source):
        raise ValueError('npm TGZ and World source differ; do not publish different payloads for the same version')
    return archive, files
