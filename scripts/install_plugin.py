"""Patch a known Coopanion plugin installation; never touch account settings."""
import argparse,datetime,json,shutil,subprocess,sys
from pathlib import Path
from coopanion_soft_voice.config import reference,REFERENCE_TEXT

WORKER='''import argparse,json
from pathlib import Path
from coopanion_soft_voice.cli import worker
p=argparse.ArgumentParser();p.add_argument('--root',required=True)
a,_=p.parse_known_args()
c=json.loads((Path(a.root)/'softvoice-profile.json').read_text(encoding='utf-8'))
worker(c['runtime'],c.get('mode','gpu'))
'''
PREFLIGHT='''import argparse,json
from pathlib import Path
from coopanion_soft_voice.cli import doctor
p=argparse.ArgumentParser();p.add_argument('--root',required=True)
a,_=p.parse_known_args()
try:
 c=json.loads((Path(a.root)/'softvoice-profile.json').read_text(encoding='utf-8'))
 print('@@COSY@@'+json.dumps(doctor(c['runtime'],c.get('mode','gpu')),ensure_ascii=False))
except Exception as e:
 print('@@COSY@@'+json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));raise SystemExit(1)
'''

def patch_runtime(source):
    if "游戏模式：仅播放原声缓存" not in source:
        source=source.replace("this.stage('ready', this.preflightResult?.backend === 'kokoro' ?",
            "this.stage('ready', this.preflightResult?.backend === 'cache-only' ? '游戏模式：仅播放原声缓存，其他回复仅文字' : this.preflightResult?.backend === 'kokoro' ?")
    if 'softVoiceProfile() {' in source:return source
    replacements={
        "  python() { return join(this.root, 'venv', 'Scripts', 'python.exe'); }":
        "  softVoiceProfile() { const p=join(this.root,'softvoice-profile.json'); return existsSync(p) ? JSON.parse(readFileSync(p,'utf8')) : null; }\n  python() { return this.softVoiceProfile()?.python || join(this.root, 'venv', 'Scripts', 'python.exe'); }",
        '  modelDir() { ':"  modelDir() { const soft=this.softVoiceProfile(); if(soft) return join(soft.runtime,'clone-model'); ",
        '  hasLocalFiles() {':"  hasLocalFiles() {\n    if(this.softVoiceProfile()) return existsSync(this.python()) && (this.softVoiceProfile().mode === 'cache' || existsSync(join(this.modelDir(),'config.json'))) && existsSync(this.softVoiceProfile().referenceAudio);",
        '  async prepareModel() {':"  async prepareModel() {\n    if(this.softVoiceProfile()) { await this.preflight(); return; }",
        '    const model = validateModel(this.modelDir());':"    const model = this.softVoiceProfile() ? {ok:this.preflightResult?.ok === true,missing:[]} : validateModel(this.modelDir());",
        "sourceReady: existsSync(join(this.sourceDir(), 'cosyvoice', 'cli', 'cosyvoice.py')),":"sourceReady: this.softVoiceProfile() ? this.preflightResult?.ok === true : existsSync(join(this.sourceDir(), 'cosyvoice', 'cli', 'cosyvoice.py')),",
        '  async _install({ allowInstall = false } = {}) {':"  async _install({ allowInstall = false } = {}) {\n    if(this.softVoiceProfile()) { await this.preflight(); this.stage('installed','Qwen soft voice preflight passed'); return; }"
    }
    for old,new in replacements.items():
        if source.count(old)!=1:raise ValueError('Unsupported plugin source; expected exactly one anchor: '+old)
        source=source.replace(old,new)
    return source

def install(plugin,runtime,mode='gpu',enable=True):
    plugin=Path(plugin).resolve();runtime=Path(runtime).resolve()
    package=json.loads((plugin/'package.json').read_text(encoding='utf-8'))
    if package.get('name')!='cortico-world-cosyvoice-tts' or package.get('version')!='0.1.11':
        raise ValueError('Only cortico-world-cosyvoice-tts 0.1.11 is supported')
    if mode not in ('gpu','cache'):raise ValueError('Unsupported mode')
    subprocess.run([sys.executable,'-m','coopanion_soft_voice.cli','--runtime',str(runtime),'doctor','--mode',mode],check=True)
    source=patch_runtime((plugin/'src/runtime.js').read_text(encoding='utf-8'))
    root=plugin/'.cosyvoice-tts';root.mkdir(exist_ok=True)
    relative=['src/runtime.js','runtime/worker.py','runtime/preflight.py','.cosyvoice-tts/settings.json','.cosyvoice-tts/softvoice-profile.json']
    backup=root/'softvoice-backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    entries=[]
    for name in relative:
        original=plugin/name;target=backup/name
        entries.append({'path':name,'existed':original.exists()})
        if original.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
    (backup/'backup.json').write_text(json.dumps({'plugin':str(plugin),'files':entries},indent=2),encoding='utf-8')
    try:
        (plugin/'src/runtime.js').write_text(source,encoding='utf-8')
        (plugin/'runtime/worker.py').write_text(WORKER,encoding='utf-8')
        (plugin/'runtime/preflight.py').write_text(PREFLIGHT,encoding='utf-8')
        settings_path=root/'settings.json'
        settings=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
        # Real plugin settings nest the voice parameters under config.
        config=settings.setdefault('config',{})
        config.update(referenceAudio=str(reference()),referenceText=REFERENCE_TEXT,speed=1)
        config.setdefault('volume',65)
        settings['speechEnabled']=bool(enable)
        settings_path.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'softvoice-profile.json').write_text(json.dumps({'python':sys.executable,'runtime':str(runtime),'referenceAudio':str(reference()),'mode':mode},indent=2),encoding='utf-8')
    except BaseException:
        restore(backup);raise
    print('Installed. Restart Coopanion to reload JavaScript. Backup: '+str(backup))

def restore(backup):
    backup=Path(backup).resolve();data=json.loads((backup/'backup.json').read_text(encoding='utf-8'))
    plugin=Path(data['plugin']).resolve()
    for item in data['files']:
        dest=(plugin/item['path']).resolve()
        if not dest.is_relative_to(plugin):raise ValueError('Unsafe backup target')
        if item['existed']:shutil.copy2(backup/item['path'],dest)
        else:dest.unlink(missing_ok=True)
    print('Backup restored. Restart Coopanion.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plugin');p.add_argument('--runtime',default='.runtime');p.add_argument('--restore')
    p.add_argument('--mode',choices=['gpu','cache'],default='gpu');p.add_argument('--keep-disabled',action='store_true')
    args=p.parse_args()
    if args.restore:restore(args.restore)
    elif args.plugin:install(args.plugin,args.runtime,args.mode,not args.keep_disabled)
    else:p.error('--plugin or --restore is required')
