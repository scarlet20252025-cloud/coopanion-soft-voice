"""Bind a relocatable, checked portable bundle to this machine's integrated GPU.

--list-devices lets the installer enumerate Vulkan GPUs before binding, so a
machine without an integrated GPU can be asked to name its discrete GPU instead
of failing with an empty integrated list.
"""
import argparse,hashlib,json,os,sys
from pathlib import Path
from coopanion_soft_voice.native_engine import settings,select_integrated_name,explicit_device,vulkan_devices


def inventory():
    devices=vulkan_devices()
    return {'devices':devices,'integrated':[d['name'] for d in devices if d['kind']=='integrated']}


def bind(root,name=None):
    root=Path(root).resolve();meta=json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))
    if meta.get('format')!=1:raise ValueError('Unsupported portable bundle format')
    cfg=meta['runtime'].copy()
    for key in ['dll','model','codec']:
        path=(root/cfg[key]).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing portable '+key)
        cfg[key]=str(path)
    cfg['dllDirectories']=[str((root/'native').resolve())]
    if name:
        device=explicit_device(name);cfg.update(deviceName=device['name'],deviceType=device['kind'],deviceSelectedExplicitly=True)
    else:cfg.update(deviceName=select_integrated_name(),deviceType='integrated',deviceSelectedExplicitly=False)
    features=root/'voice-features.json'
    if hashlib.sha256(features.read_bytes()).hexdigest()!=cfg['speechOnly']['featuresSha256']:
        raise ValueError('Portable voice features checksum mismatch')
    temp=root/'native-runtime.json.partial'
    temp.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    os.replace(temp,root/'native-runtime.json')
    settings(root,cached_verification=True)
    return {'runtime':str(root),'device':cfg['deviceName'],'version':meta['version'],'author':meta['author']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root')
    p.add_argument('--device-name')
    p.add_argument('--list-devices',action='store_true',help='Print detected Vulkan GPUs as JSON and exit')
    a=p.parse_args()
    if a.list_devices:
        print(json.dumps(inventory(),ensure_ascii=False));sys.exit(0)
    if not a.root:p.error('--root is required unless --list-devices is used')
    print(json.dumps(bind(a.root,a.device_name),ensure_ascii=False))
