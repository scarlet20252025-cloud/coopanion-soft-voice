"""Verified code-only updates for the portable runtime. Models and user settings stay put."""
import argparse,hashlib,json,os,re,subprocess,sys,tempfile,time,urllib.request,zipfile
from pathlib import Path,PurePosixPath
from . import __version__

REPO='scarlet20252025-cloud/coopanion-soft-voice'
POINTER=f'https://raw.githubusercontent.com/{REPO}/main/update-release.json'
MAX_ZIP=32*1024*1024
MAX_FILES=64*1024*1024

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Invalid release version')
    return tuple(map(int,value.split('.')))

def emit(stage,detail,**extra):
    print('@@UPDATE@@'+json.dumps({'stage':stage,'detail':detail,**extra},ensure_ascii=False),flush=True)

def descriptor(data):
    if data.get('format')!=1 or data.get('platform')!='windows-x64':raise ValueError('Unsupported update format/platform')
    version(data['version']);version(data['worldVersion']);version(data['minimumVersion'])
    patch=data['patch'];name=patch['file']
    if not re.fullmatch(r'coopanion-voice-update-\d+\.\d+\.\d+\.zip',name):raise ValueError('Invalid update filename')
    expected=f'https://github.com/{REPO}/releases/download/v{data["version"]}/{name}'
    if patch['url']!=expected or not re.fullmatch(r'[0-9a-f]{64}',patch['sha256']):raise ValueError('Untrusted update URL/checksum')
    if type(patch['bytes']) is not int or not 0<patch['bytes']<=MAX_ZIP:raise ValueError('Update exceeds size limit')
    return data

def portable(root):
    root=Path(root).resolve()
    if not (root/'portable-manifest.json').is_file():raise ValueError('Code hot update requires the portable installation; source installations use git pull or the complete ZIP')
    if Path(sys.executable).resolve()!=root/'python/python.exe':raise ValueError('Run the portable package Python for hot update')
    return root

def check(root):
    root=Path(root).resolve()
    emit('checking','Checking the official GitHub release descriptor')
    with urllib.request.urlopen(urllib.request.Request(POINTER,headers={'User-Agent':'Asryto-local-voice-updater'}),timeout=20) as response:
        data=response.read(65537)
    if len(data)>65536:raise ValueError('Release descriptor exceeds size limit')
    release=descriptor(json.loads(data))
    supported=(root/'portable-manifest.json').is_file() and Path(sys.executable).resolve()==root/'python/python.exe'
    current=__version__
    if supported:current=json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))['version']
    recovery=(root/'updates/pending.json').exists()
    available=version(release['version'])>version(current) or recovery
    emit('available' if available else 'current','Update available' if available else 'Already current',
         release=release,currentVersion=current,available=available,supported=supported,needsRecovery=recovery,
         releaseUrl=f'https://github.com/{REPO}/releases/tag/v{release["version"]}')
    return release

def permitted(name,release_version):
    p=PurePosixPath(name)
    if p.is_absolute() or '\\' in name or ':' in name or any(x in ('..','.') for x in p.parts):return False
    if name.startswith('python/coopanion_soft_voice/'):
        return p.suffix in ('.py','.json','.wav','.txt') and '__pycache__' not in p.parts
    if name.startswith(f'python/coopanion_soft_voice-{release_version}.dist-info/'):
        return p.name in ('METADATA','WHEEL','RECORD','top_level.txt','entry_points.txt','LICENSE')
    if name.startswith('world/'):
        return name in ('world/package.json','world/README.md','world/LICENSE') or (len(p.parts)>2 and p.parts[1] in ('src','dist') and p.suffix in ('.js','.css','.md','.py'))
    if name.startswith('scripts/'):
        return len(p.parts)==2 and p.name in ('activate_portable.py','verify_deployment.py','install_world.py','install_bubble_bridge.py','install-portable.ps1','find-coopanion.ps1','collect-diagnostics.ps1','collect_diagnostics.py','report_issue.py')
    return name in ('README.md','collect-diagnostics.cmd') or (len(p.parts)==2 and p.parts[0]=='docs' and p.suffix=='.md')

def unpack(archive,release):
    if Path(archive).stat().st_size>MAX_ZIP:raise ValueError('Update exceeds size limit')
    raw=Path(archive).read_bytes()
    if len(raw)!=release['patch']['bytes'] or hashlib.sha256(raw).hexdigest()!=release['patch']['sha256']:raise ValueError('Update ZIP checksum/size mismatch')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)>1500:raise ValueError('Duplicate or excessive ZIP members')
        if sum(i.file_size for i in z.infolist())>MAX_FILES:raise ValueError('Expanded update exceeds size limit')
        meta=json.loads(z.read('patch-manifest.json'))
        if meta.get('format')!=1 or meta.get('version')!=release['version'] or meta.get('worldVersion')!=release['worldVersion']:raise ValueError('Patch metadata mismatch')
        hashes=meta['files']
        if set(names)!=(set(hashes)|{'patch-manifest.json'}):raise ValueError('Unexpected ZIP members')
        files={}
        for name,digest in hashes.items():
            info=z.getinfo(name)
            if not permitted(name,release['version']) or ((info.external_attr>>16)&0o170000)==0o120000:raise ValueError('Unsafe update member: '+name)
            data=z.read(name)
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Patch file checksum mismatch: '+name)
            if name.endswith('.py'):compile(data,name,'exec')
            files[name]=data
    return meta,files

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.voice-update-tmp')
    temporary.write_bytes(data);os.replace(temporary,path)

def world_targets(extensions):
    if extensions is None:return []
    base=Path(extensions).resolve();name='cortico-world-soft-voice'
    if name not in json.loads((base/'package.json').read_text(encoding='utf-8-sig')).get('dependencies',{}):raise ValueError('Voice extension is not registered here')
    alias=base/'node_modules'/name;target=alias.resolve(strict=True);local=base/'local-soft-voice'
    if target!=alias.absolute() and not target.is_relative_to((base/'node_modules/.pnpm').resolve()):raise ValueError('Extension link escapes pnpm store')
    if local.resolve()!=local.absolute():raise ValueError('Local extension must not be a symlink/junction')
    for folder in (target,local):
        if json.loads((folder/'package.json').read_text(encoding='utf-8'))['name']!=name:raise ValueError('Unexpected installed World')
    return [target,local]

def managed_roots(root,worlds):
    return [root/'python/Lib/site-packages',root/'world',root/'scripts',root/'docs',root/'README.md',root/'collect-diagnostics.cmd',root/'portable-manifest.json',*worlds]

def restore(journal,roots):
    entries=json.loads(journal.read_text(encoding='utf-8'))['files']
    for i,entry in enumerate(reversed(entries)):
        dest=Path(entry['target']).resolve();backup=Path(entry['backup']).resolve()
        if not any(dest.is_relative_to(r) for r in roots) or not backup.is_relative_to(journal.parent/'backups'):raise ValueError('Unsafe recovery journal')
        if entry['existed']:atomic(dest,backup.read_bytes())
        elif dest.exists():dest.unlink()
        emit('restoring','Restoring previous code',completed=i+1,total=len(entries))
    journal.unlink()

def install_archive(root,archive,release,extensions=None,verify=None):
    """All files validated before writes. Journal recovers interruption; exceptions roll back."""
    root=Path(root).resolve();release=descriptor(release);meta,files=unpack(archive,release)
    cfg=json.loads((root/'native-runtime.json').read_text(encoding='utf-8'))
    actual={'dll':cfg['dllSha256'],**cfg.get('speechOnly',{}).get('hashes',{})}
    if actual!=meta['runtimeHashes']:raise ValueError('This update is incompatible with the installed native/model profile; use complete ZIP')
    site=root/'python/Lib/site-packages';worlds=[root/'world',*world_targets(extensions)]
    roots=managed_roots(root,worlds)
    cache=root/'updates';cache.mkdir(exist_ok=True);journal=cache/'pending.json'
    if journal.exists():restore(journal,roots)
    current=json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))
    if version(current['version'])<version(release['minimumVersion']) or version(current['version'])>=version(release['version']):raise ValueError('Update requires an older supported portable version; refusing downgrade or reinstall')
    planned={}
    for name,data in files.items():
        if name.startswith('python/'):targets=[site/name[7:]]
        elif name.startswith('world/'):targets=[w/name[6:] for w in worlds]
        else:targets=[root/name]
        for target in targets:
            target=target.resolve()
            if not any(target.is_relative_to(r) for r in roots):raise ValueError('Update target escapes installation')
            planned[target]=data
    world_changed=bool(extensions) and any(
        not (worlds[1]/name[6:]).is_file() or (worlds[1]/name[6:]).read_bytes()!=data
        for name,data in files.items() if name.startswith(('world/src/','world/dist/')) or name=='world/package.json')
    for old in site.glob('coopanion_soft_voice-*.dist-info'):
        if old.name!=f'coopanion_soft_voice-{release["version"]}.dist-info':
            if old.resolve()!=old.absolute():raise ValueError('Old package metadata must not be a link')
            for file in old.rglob('*'):
                if file.is_file():
                    if not file.resolve().is_relative_to(site):raise ValueError('Metadata file escapes package directory')
                    planned[file.resolve()]=None
    current.update(version=release['version'],worldVersion=release['worldVersion'])
    planned[root/'portable-manifest.json']=json.dumps(current,indent=2).encode('utf-8')
    backup=cache/'backups'/str(time.time_ns());backup.mkdir(parents=True)
    entries=[]
    emit('backing_up','Backing up previous code',completed=0,total=len(planned))
    for i,target in enumerate(planned):
        existed=target.exists();saved=backup/str(i)
        if existed:saved.write_bytes(target.read_bytes())
        entries.append({'target':str(target),'backup':str(saved),'existed':existed})
        emit('backing_up','Backing up previous code',completed=i+1,total=len(planned))
    atomic(journal,json.dumps({'files':entries}).encode('utf-8'))
    try:
        for i,(target,data) in enumerate(planned.items()):
            if data is None:target.unlink(missing_ok=True)
            else:atomic(target,data)
            emit('installing','Installing verified code',completed=i+1,total=len(planned))
        emit('verifying','Checking the updated runtime')
        if verify:verify()
        else:subprocess.run([sys.executable,'-m','coopanion_soft_voice.cli','--runtime',str(root),'doctor','--mode','igpu'],check=True,capture_output=True,timeout=60)
    except BaseException:
        restore(journal,roots);emit('rolled_back','Update failed; previous code restored');raise
    journal.unlink()
    for old in site.glob('coopanion_soft_voice-*.dist-info'):
        if old.name!=f'coopanion_soft_voice-{release["version"]}.dist-info':
            for folder in sorted((p for p in old.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                try:folder.rmdir()
                except OSError:pass
            try:old.rmdir()
            except OSError:pass
    emit('installed','Voice engine code updated; changed World code loads after restarting Coopanion',version=release['version'],worldVersion=release['worldVersion'],requiresRestart=world_changed,backup=str(backup))

def apply(root,extensions=None):
    root=portable(root)
    folder=root/'updates';folder.mkdir(exist_ok=True)
    # OS locks disappear if the updater crashes; pending.json restores interrupted writes.
    with (folder/'update.lock').open('a+b') as lock:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journal=folder/'pending.json'
        if journal.exists():restore(journal,managed_roots(root,world_targets(extensions)))
        release=check(root)
        current=json.loads((root/'portable-manifest.json').read_text(encoding='utf-8'))['version']
        if version(release['version'])<=version(current):return
        with tempfile.TemporaryDirectory(prefix='voice-update-',dir=folder) as temp:
            archive=Path(temp)/release['patch']['file'];received=0
            emit('downloading','Downloading code-only update',received=0,total=release['patch']['bytes'])
            with urllib.request.urlopen(urllib.request.Request(release['patch']['url'],headers={'User-Agent':'Asryto-local-voice-updater'}),timeout=20) as response,archive.open('wb') as target:
                while chunk:=response.read(128*1024):
                    received+=len(chunk)
                    if received>release['patch']['bytes']:raise ValueError('Download exceeds declared size')
                    target.write(chunk);emit('downloading','Downloading code-only update',received=received,total=release['patch']['bytes'])
            emit('validating','Checking archive and file SHA256')
            install_archive(root,archive,release,extensions)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['check','apply']);p.add_argument('--runtime',required=True);p.add_argument('--extensions')
    args=p.parse_args()
    try:
        if args.action=='check':check(args.runtime)
        else:apply(args.runtime,args.extensions)
    except Exception as error:
        emit('error',str(error));raise SystemExit(1)

if __name__=='__main__':main()
