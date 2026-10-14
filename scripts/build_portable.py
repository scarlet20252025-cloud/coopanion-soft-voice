"""Build a relocatable offline runtime; no venv, installed Python or author paths in ZIP."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'src'))
PYTHON_SHA256='4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
    return h.hexdigest()

def extract(archive,target):
    target=Path(target).resolve();target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (target/name).resolve().is_relative_to(target):raise ValueError('Unsafe archive member')
        z.extractall(target)

def build(args):
    out=Path(args.output).resolve()
    if out.exists():raise ValueError('Use a new output directory')
    profile=Path(args.profile).resolve();cfg=json.loads((profile/'native-runtime.json').read_text())
    if not cfg.get('speechOnly') or not cfg.get('streamTextEmbedding'):raise ValueError('Expected fixed-reference text-rows profile')
    if digest(args.python_zip)!=PYTHON_SHA256:raise ValueError('Unexpected Python embeddable ZIP')
    out.mkdir(parents=True);native=out/'native';models=out/'models';native.mkdir();models.mkdir()
    for key in ['model','codec']:
        if digest(cfg[key])!=cfg['speechOnly']['hashes'][key]:raise ValueError('Unexpected '+key)
        name=Path(cfg[key]).name;shutil.copyfile(cfg[key],models/name);cfg[key]='models/'+name
    for file in ['libqwen.dll','libc++.dll','libunwind.dll']:
        source=Path(args.dll) if file=='libqwen.dll' else Path(args.dll_dir)/file
        shutil.copyfile(source,native/file)
    cfg.update(dll='native/libqwen.dll',dllSha256=digest(native/'libqwen.dll'))
    cfg.pop('deviceName',None);cfg.pop('dllDirectories',None);cfg.pop('deviceIndex',None)
    shutil.copyfile(profile/'voice-features.json',out/'voice-features.json')
    extract(args.python_zip,out/'python')
    site=out/'python/Lib/site-packages';site.mkdir(parents=True)
    dependencies=json.loads((Path(args.wheels)/'manifest.json').read_text(encoding='utf-8'))
    if {d['name'] for d in dependencies}!={'numpy','soundfile','sounddevice','cffi','pycparser'}:raise ValueError('Unexpected dependencies')
    for item in dependencies:
        wheel=Path(args.wheels)/item['file']
        if wheel.parent.resolve()!=Path(args.wheels).resolve() or digest(wheel)!=item['sha256']:raise ValueError('Wheel checksum mismatch')
        extract(wheel,site)
    extract(args.package_wheel,site)
    (out/'python/python312._pth').write_text('python312.zip\n.\nLib/site-packages\nimport site\n',encoding='utf-8')
    shutil.copytree(ROOT/'world',out/'world',ignore=shutil.ignore_patterns('__pycache__','*.pyc','test'))
    scripts=out/'scripts';scripts.mkdir()
    for file in ['activate_portable.py','verify_deployment.py','install_world.py','install_bubble_bridge.py','install-portable.ps1','find-coopanion.ps1','collect-diagnostics.ps1','report_issue.py']:
        shutil.copyfile(ROOT/'scripts'/file,scripts/file)
    shutil.copyfile(ROOT/'src/coopanion_soft_voice/diagnostics.py',scripts/'collect_diagnostics.py')
    shutil.copyfile(ROOT/'collect-diagnostics.cmd',out/'collect-diagnostics.cmd')
    (out/'install.cmd').write_text('@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\install-portable.ps1" %*\r\nif errorlevel 1 pause\r\n',encoding='ascii')
    for file in ['LICENSE','THIRD_PARTY_NOTICES.md']:shutil.copyfile(ROOT/file,out/file)
    licenses=out/'licenses';licenses.mkdir()
    for name in ['qwentts-MIT.txt','ggml-MIT.txt','llvm-mingw-LICENSE.txt','models-APACHE-2.0.txt']:
        shutil.copyfile(Path(args.licenses)/name,licenses/name)
    shutil.copytree(ROOT/'docs',out/'docs')
    (out/'README.md').write_text((ROOT/'docs/PORTABLE_INSTALL.md').read_text(encoding='utf-8').replace('(INSTALL_WITHOUT_MARKET.md)','(docs/INSTALL_WITHOUT_MARKET.md)'),encoding='utf-8')
    from coopanion_soft_voice import __version__
    meta={'format':1,'version':__version__,'worldVersion':json.loads((ROOT/'world/package.json').read_text(encoding='utf-8'))['version'],'author':'Asryto','python':'3.12.10','nativeCPU':'generic',
          'nativeSource':'51512f129a7419567f4b8abfb06801451789b8f1','dependencies':dependencies,'runtime':cfg}
    (out/'portable-manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    archive=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for file in sorted(out.rglob('*')):
            if file.is_file():z.write(file,str(file.relative_to(out)).replace('\\','/'))
    report={'file':archive.name,'bytes':archive.stat().st_size,'sha256':digest(archive),'author':'Asryto'}
    archive.with_suffix('.zip.sha256').write_text(report['sha256']+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['profile','dll','dll-dir','python-zip','wheels','package-wheel','licenses','output']:p.add_argument('--'+name,required=True)
    build(p.parse_args())
