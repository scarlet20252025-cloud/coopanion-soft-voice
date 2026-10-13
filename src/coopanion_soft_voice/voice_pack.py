"""Versioned, data-only reference voice packages. No archive paths are extracted."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import wave
import zipfile

MAX_ZIP = 2 * 1024 * 1024
MAX_AUDIO = 800000

def validate(manifest, audio):
    if not isinstance(manifest, dict) or manifest.get('format') != 'local-voice-pack' or manifest.get('version') != 1:
        raise ValueError('音色包格式须为 local-voice-pack version 1')
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,47}', str(manifest.get('id', ''))):
        raise ValueError('音色 ID 须为 3–48 位小写字母、数字或连字符')
    for key, limit in [('name', 60), ('referenceText', 300)]:
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(key + ' 无效或过长')
    if manifest.get('language') != 'Chinese':
        raise ValueError('当前版本仅支持 Chinese 音色包')
    if len(audio) > MAX_AUDIO or hashlib.sha256(audio).hexdigest() != manifest.get('sha256'):
        raise ValueError('参考音频过大或 SHA256 不匹配')
    with wave.open(io.BytesIO(audio), 'rb') as wav:
        if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (1, 24000, 2, 'NONE'):
            raise ValueError('参考音频必须为 24 kHz 单声道 PCM16 WAV')
        duration = wav.getnframes() / 24000
        if not 3 <= duration <= 15:
            raise ValueError('参考音频应为 3–15 秒')
        frames = wav.readframes(wav.getnframes())
        if len(frames) != wav.getnframes() * 2:
            raise ValueError('参考音频被截断')
        import array
        samples = array.array('h', frames)
        peak = max(abs(x) for x in samples)
        if peak < 100: raise ValueError('参考音频几乎无声')
    # Only approved scalar fields survive; paths/instructions in ZIP metadata are ignored.
    return {k: manifest[k].strip() if isinstance(manifest[k], str) else manifest[k]
            for k in ('format', 'version', 'id', 'name', 'referenceText', 'language', 'sha256')} | {'duration': duration}

def read_zip(path):
    if Path(path).stat().st_size > MAX_ZIP: raise ValueError('ZIP 不得超过 2 MiB')
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if sorted(x.filename for x in entries) != ['reference.wav', 'voice.json']:
            raise ValueError('ZIP 根目录必须且只能包含 voice.json 和 reference.wav')
        for item in entries:
            if item.flag_bits & 1 or item.file_size > (16000 if item.filename == 'voice.json' else MAX_AUDIO):
                raise ValueError('不支持加密或超限的音色包')
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('不支持符号链接')
        audio = z.read('reference.wav')
        manifest = json.loads(z.read('voice.json').decode('utf-8'))
    return validate(manifest, audio), audio

def install(archive, root):
    manifest, audio = read_zip(archive)
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=True)
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    key = manifest['id'] + '-' + identity
    dest = root / key
    if dest.exists():
        load(dest)
        return dict(manifest, key=key)
    tmp = Path(tempfile.mkdtemp(prefix='.import-', dir=root))
    try:
        (tmp / 'reference.wav').write_bytes(audio)
        (tmp / 'voice.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.rename(dest)
    finally:
        if tmp.exists(): shutil.rmtree(tmp)
    return dict(manifest, key=key)

def load(folder):
    folder = Path(folder).resolve()
    audio = folder / 'reference.wav'
    manifest = validate(json.loads((folder / 'voice.json').read_text(encoding='utf-8')), audio.read_bytes())
    return audio, manifest

def create(wav, output, voice_id, name, text):
    audio = Path(wav).read_bytes()
    manifest = validate({'format': 'local-voice-pack', 'version': 1, 'id': voice_id, 'name': name,
        'referenceText': text, 'language': 'Chinese', 'sha256': hashlib.sha256(audio).hexdigest()}, audio)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('voice.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr('reference.wav', audio)
    return manifest

def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('--zip', required=True); imp.add_argument('--root', required=True)
    make = sub.add_parser('create')
    for name in ('wav', 'output', 'id', 'name', 'text'): make.add_argument('--' + name, required=True)
    a = p.parse_args()
    result = install(a.zip, a.root) if a.command == 'import' else create(a.wav, a.output, a.id, a.name, a.text)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__': main()
