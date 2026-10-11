import hashlib,json
from pathlib import Path

REFERENCE_SHA256='4d47133ec965474fb546110c521541d0a6d610f8b84a02b1a575404c6fa63f20'
REFERENCE_TEXT='今天也辛苦啦，先休息一小会儿，我会乖乖等你。'
MODEL_REPO='Qwen/Qwen3-TTS-12Hz-0.6B-Base'
MODEL_REVISION='5d83992436eae1d760afd27aff78a71d676296fc'

def reference():
    path=Path(__file__).parent/'assets/soft-child-design-2.wav'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=REFERENCE_SHA256:
        raise ValueError('Accepted reference WAV checksum mismatch; restore the packaged asset.')
    return path.resolve()

def profile(runtime):
    return {'qwenRuntime':str(Path(runtime).resolve()),'referenceAudio':str(reference()),
            'referenceText':REFERENCE_TEXT,'seed':44,'precision':'bfloat16'}

def manifest():
    return json.loads((Path(__file__).parent/'model-manifest.json').read_text(encoding='utf-8'))

def validate_model(runtime,hashes=False):
    root=Path(runtime)/'clone-model'
    for item in manifest()['files']:
        if item['type']!='file' or item['path'] in ('.gitattributes','README.md'):continue
        path=root/item['path']
        if not path.is_file() or path.stat().st_size!=item['size']:
            raise ValueError('Missing or incomplete model file: '+item['path'])
        if hashes and item.get('lfs',{}).get('oid'):
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
            if digest.hexdigest()!=item['lfs']['oid']:raise ValueError('Model checksum mismatch: '+item['path'])
    return root.resolve()
