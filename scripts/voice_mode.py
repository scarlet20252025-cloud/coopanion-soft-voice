"""Inspect or select an installed voice mode without enabling speech or loading a model."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile


def select_mode(plugin, mode=None):
    root=Path(plugin).resolve()/'.cosyvoice-tts'
    path=root/'softvoice-profile.json'
    profile=json.loads(path.read_text(encoding='utf-8'))
    settings=json.loads((root/'settings.json').read_text(encoding='utf-8'))
    backup=None
    if mode is not None:
        if mode not in ('gpu','cache','igpu'):raise ValueError('Unsupported mode')
        if mode=='igpu':
            from coopanion_soft_voice.cli import doctor
            doctor(profile['runtime'],'igpu')
        if mode=='gpu' and not (Path(profile['runtime'])/'clone-model/config.json').is_file():
            raise ValueError('GPU model files missing; mode not changed')
        if profile.get('mode','gpu')!=mode:
            backup=root/'softvoice-backups'/('mode-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            backup.mkdir(parents=True)
            shutil.copy2(path,backup/path.name)
            profile['mode']=mode
            temp=None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=root,delete=False) as f:
                    temp=Path(f.name);json.dump(profile,f,ensure_ascii=False,indent=2)
                os.replace(temp,path)
            finally:
                if temp and temp.exists():temp.unlink()
    return {'mode':profile.get('mode','gpu'),'speechEnabled':settings.get('speechEnabled',False),
            'restartRequired':backup is not None,'backup':str(backup) if backup else None,
            'note':'Restart Coopanion after changing mode. GPU mode requires GPU memory; cache mode never runs inference.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin',required=True)
    parser.add_argument('--mode',choices=['gpu','cache','igpu'])
    args=parser.parse_args()
    print(json.dumps(select_mode(args.plugin,args.mode),ensure_ascii=False,indent=2))
