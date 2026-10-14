"""Install the standalone World; no dependency on another speech plugin."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import importlib.util
import os
import uuid

NAME = 'cortico-world-soft-voice'


def package_target(extensions):
    extensions=Path(extensions).resolve()
    alias=extensions/'node_modules'/NAME
    if not alias.is_symlink():return alias
    target=alias.resolve(strict=True)
    virtual_store=extensions/'node_modules/.pnpm'
    if not target.is_relative_to(virtual_store.resolve()) or target.name!=NAME:
        raise ValueError('Extension link points outside its pnpm virtual store; refusing to change it')
    return target


def copy_package(source,target):
    """Replace individual files atomically so pnpm hardlinks never mutate shared store bytes."""
    source,target=Path(source).resolve(),Path(target).resolve()
    target.mkdir(parents=True,exist_ok=True)
    for part in ['src','dist','package.json','LICENSE','README.md']:
        item=source/part
        files=[item] if item.is_file() else [p for p in item.rglob('*') if p.is_file()]
        for file in files:
            if '__pycache__' in file.parts or file.suffix=='.pyc':continue
            dest=target/file.relative_to(source)
            if not dest.resolve().is_relative_to(target):raise ValueError('Package file target escapes extension directory')
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_name(dest.name+'.install-'+uuid.uuid4().hex)
            shutil.copyfile(file,temp)
            os.replace(temp,dest)

def install(extensions, bot, runtime, enable=False):
    extensions, bot, runtime = map(lambda p: Path(p).resolve(), (extensions, bot, runtime))
    if 'cortico-world-cosyvoice-tts' in sys.base_prefix.lower():
        raise ValueError('Python still belongs to the old plugin. Run setup-native.ps1 with an independent Python 3.10 installation first.')
    source = Path(__file__).resolve().parents[1] / 'world'
    subprocess.run([sys.executable, '-m', 'coopanion_soft_voice.cli', '--runtime', str(runtime), 'doctor', '--mode', 'igpu'], check=True)
    ep, bp = extensions / 'package.json', bot / 'config.json'
    ext, config = json.loads(ep.read_text(encoding='utf-8-sig')), json.loads(bp.read_text(encoding='utf-8-sig'))
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = bot / 'data' / 'soft-voice' / 'backups' / stamp
    backup.mkdir(parents=True)
    shutil.copy2(ep, backup / 'extensions-package.json')
    shutil.copy2(bp, backup / 'bot-config.json')
    dest = package_target(extensions)
    local = extensions / 'local-soft-voice'
    if local.is_symlink():raise ValueError('local-soft-voice must be a physical package directory')
    if dest.exists():
        shutil.copytree(dest, backup / 'previous-package')
    if local.exists():shutil.copytree(local,backup/'previous-local-package')
    copy_package(source,dest)
    data = bot / 'data' / 'soft-voice'
    profile = {'python': sys.executable, 'runtime': str(runtime), 'mode': 'igpu'}
    for name in ['runtime-profile.json', 'settings.json']:
        if (data / name).exists(): shutil.copy2(data / name, backup / name)
    (data / 'runtime-profile.json').write_text(json.dumps(profile, indent=2), encoding='utf-8')
    settings = data / 'settings.json'
    saved = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {'config': {'volume': 65}}
    if enable:saved['speechEnabled'] = True
    else:saved.setdefault('speechEnabled',False)
    settings.write_text(json.dumps(saved, indent=2), encoding='utf-8')
    copy_package(source,local)
    ext.setdefault('dependencies', {})[NAME] = 'file:./local-soft-voice'
    # Unregister legacy package without deleting its files or personal backups.
    ext['dependencies'].pop('cortico-world-cosyvoice-tts', None)
    worlds = config.setdefault('worlds', {})
    worlds.pop('cosyvoice-tts', None)
    worlds.setdefault('soft-voice', {})['enabled'] = True
    ep.write_text(json.dumps(ext, ensure_ascii=False, indent=2), encoding='utf-8')
    bp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    desktop = extensions.parent.parent / 'resources/app/node_modules/cortico-world-desktop-pet'
    if desktop.is_dir():
        spec = importlib.util.spec_from_file_location('voice_bubble_installer', Path(__file__).with_name('install_bubble_bridge.py'))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        try: helper.install_bridge(desktop)
        except ValueError as error: print('Bubble bridge not applied:', error)
    print('Installed standalone soft-voice. Restart Coopanion. Backup:', backup)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--extensions', required=True)
    p.add_argument('--bot', required=True)
    p.add_argument('--runtime', required=True)
    p.add_argument('--enable', action='store_true')
    a = p.parse_args()
    install(a.extensions, a.bot, a.runtime, a.enable)
