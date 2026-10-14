"""Select or build the verified fixed-reference profile using only this installation."""
import argparse,hashlib,json,subprocess,sys,uuid
from pathlib import Path
from coopanion_soft_voice.native_engine import settings,MODEL_HASHES
from coopanion_soft_voice.config import REFERENCE_SHA256
from coopanion_soft_voice import reference_cache


def prepare(runtime):
    root=Path(runtime).resolve();cfg=settings(root,cached_verification=True)
    if cfg.get('speechOnly'):raise ValueError('Supply the full runtime produced by setup-native.ps1')
    identity={k:cfg.get(k) for k in ['dllSha256','deviceName','kvContext','compactGraphs','streamTextEmbedding']}
    identity.update(sourceHashes=MODEL_HASHES,referenceSha256=REFERENCE_SHA256)
    tag=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    dest=root/('speech-only-'+tag)
    if not dest.exists():
        stage=root/(dest.name+'.partial-'+uuid.uuid4().hex[:8])
        subprocess.run([sys.executable,str(Path(__file__).with_name('build_speech_only.py')),
                        '--runtime',str(root),'--output',str(stage)],check=True,stdout=sys.stderr)
        # build_speech_only records absolute model paths; update them before publishing.
        manifest=json.loads((stage/'native-runtime.json').read_text(encoding='utf-8'))
        for key in ['model','codec']:manifest[key]=str(dest/Path(manifest[key]).name)
        (stage/'native-runtime.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        stage.rename(dest)
    final=settings(dest,cached_verification=True)
    fixed=final.get('speechOnly',{})
    if (fixed.get('referenceSha256')!=REFERENCE_SHA256 or fixed.get('sourceHashes')!=MODEL_HASHES or
            any(final.get(k)!=cfg.get(k) for k in identity if k not in ['sourceHashes','referenceSha256'])):
        raise ValueError('Existing speech profile does not match the verified runtime')
    features=dest/'voice-features.json'
    if hashlib.sha256(features.read_bytes()).hexdigest()!=fixed.get('featuresSha256') or reference_cache.read(features) is None:
        raise ValueError('Invalid fixed-reference features')
    return dest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True)
    a=p.parse_args();dest=prepare(a.runtime)
    print(json.dumps({'runtime':str(dest),'profile':'fixed-reference-Q8-text-rows','referenceSha256':REFERENCE_SHA256}))
