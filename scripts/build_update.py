"""Build a small model-free update ZIP and its pinned public descriptor."""
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'src'))

def build(wheel,profile,output,world_package=None):
    from coopanion_soft_voice import __version__
    config=json.loads((Path(profile)/'native-runtime.json').read_text(encoding='utf-8'))
    world=json.loads((ROOT/'world/package.json').read_text(encoding='utf-8'))
    from coopanion_soft_voice.updates import permitted, legacy_permitted
    files={}
    with zipfile.ZipFile(wheel) as z:
        for name in z.namelist():
            if not name.endswith('/'):files['python/'+name]=z.read(name)
    from coopanion_soft_voice.world_package import pack
    _,world_files=pack(ROOT/'world',Path(output)/'packages',world_package)
    files.update({'world/'+name:data for name,data in world_files.items()})
    # Market-facing metadata (self-description, release notes) reaches installed
    # copies through npm. A patch is unpacked by the engine already on the
    # machine, so shipping a newly added name here would be rejected outright.
    for name in ('world/describe.json','world/CHANGELOG.md'):
        if files.pop(name,None) is not None:
            print(json.dumps({'notInPatch':name,'reason':'market metadata travels through npm'}))
    for folder in ('docs',):
        for file in (ROOT/folder).rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and 'test' not in file.parts and permitted(file.relative_to(ROOT).as_posix(),__version__):files[file.relative_to(ROOT).as_posix()]=file.read_bytes()
    for name in ('activate_portable.py','verify_deployment.py','install_world.py','install_bubble_bridge.py','install-portable.ps1','find-coopanion.ps1','collect-diagnostics.ps1','report_issue.py'):
        files['scripts/'+name]=(ROOT/'scripts'/name).read_bytes()
    files['scripts/gpu_memory.py']=(ROOT/'src/coopanion_soft_voice/gpu_memory.py').read_bytes()
    files['scripts/issue_reporting.py']=(ROOT/'src/coopanion_soft_voice/issue_reporting.py').read_bytes()
    files['scripts/collect_diagnostics.py']=(ROOT/'src/coopanion_soft_voice/diagnostics.py').read_bytes()
    files['collect-diagnostics.cmd']=(ROOT/'collect-diagnostics.cmd').read_bytes()
    files['README.md']=(ROOT/'docs/PORTABLE_INSTALL.md').read_text(encoding='utf-8').replace('(INSTALL_WITHOUT_MARKET.md)','(docs/INSTALL_WITHOUT_MARKET.md)').encode('utf-8')
    meta={'format':1,'version':__version__,'worldVersion':world['version'],
          'runtimeHashes':{'dll':config['dllSha256'],**config['speechOnly']['hashes']},
          'files':{name:hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    rejected=sorted(name for name in files if not legacy_permitted(name,__version__) or not permitted(name,__version__))
    if rejected:
        raise ValueError('Patch members an engine at the declared minimumVersion would reject: '+', '.join(rejected)+
                         '; raise minimumVersion in update-release.json to an engine that accepts them, and tell older installs to use the complete package')
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    archive=folder/f'coopanion-voice-update-{__version__}.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(files.items()):z.writestr(name,data)
        z.writestr('patch-manifest.json',json.dumps(meta,indent=2))
    release={'format':1,'version':__version__,'worldVersion':world['version'],'minimumVersion':'0.4.11','platform':'windows-x64',
        'runtimeHashes':meta['runtimeHashes'],
        'patch':{'file':archive.name,'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'url':f'https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/download/updates-v{__version__}/{archive.name}'}}
    from coopanion_soft_voice.updates import descriptor,unpack
    unpack(archive,descriptor(release))
    (folder/'update-release.json').write_text(json.dumps(release,indent=2),encoding='utf-8')
    archive.with_suffix('.zip.sha256').write_text(release['patch']['sha256']+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(release))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--wheel',required=True);p.add_argument('--profile',required=True);p.add_argument('--output',required=True);p.add_argument('--world-package')
    a=p.parse_args();build(a.wheel,a.profile,a.output,a.world_package)
