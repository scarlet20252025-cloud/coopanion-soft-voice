"""Bind a relocatable, checked portable bundle to this machine's integrated GPU."""
import argparse,hashlib,json,os
from pathlib import Path
from coopanion_soft_voice.native_engine import settings,select_integrated_name


def bind(root,name=None):
    root=Path(root).resolve();meta=json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))
    if meta.get('format')!=1:raise ValueError('Unsupported portable bundle format')
    cfg=meta['runtime'].copy()
    for key in ['dll','model','codec']:
        path=(root/cfg[key]).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing portable '+key)
        cfg[key]=str(path)
    cfg['dllDirectories']=[str((root/'native').resolve())]
    cfg['deviceName']=select_integrated_name(name)
    features=root/'voice-features.json'
    if hashlib.sha256(features.read_bytes()).hexdigest()!=cfg['speechOnly']['featuresSha256']:
        raise ValueError('Portable voice features checksum mismatch')
    temp=root/'native-runtime.json.partial'
    temp.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    os.replace(temp,root/'native-runtime.json')
    settings(root,cached_verification=True)
    return {'runtime':str(root),'device':cfg['deviceName'],'version':meta['version'],'author':meta['author']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--device-name')
    a=p.parse_args();print(json.dumps(bind(a.root,a.device_name),ensure_ascii=False))
