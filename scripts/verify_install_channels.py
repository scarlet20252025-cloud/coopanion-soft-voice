"""Real pnpm cross-channel smoke test against an isolated localhost registry.

No public publish, no account, no model inference, no changes to the user's app.
Tests actual registry package replacement and the exact npm payload, not GPU speed.
"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from unittest.mock import patch
import urllib.parse
import zipfile
from coopanion_soft_voice.world_package import NAME, pack, payload
from coopanion_soft_voice import updates

ROOT = Path(__file__).resolve().parents[1]


def verify(output):
    pnpm = shutil.which('pnpm.cmd') or shutil.which('pnpm')
    if not pnpm:
        raise RuntimeError('pnpm is required for this integration test')
    with tempfile.TemporaryDirectory(prefix='voice-channels-') as temp:
        base = Path(temp)
        versions, archives, packages = [], {}, {}
        original = json.loads((ROOT/'world/package.json').read_text(encoding='utf-8'))['version']
        major, minor, revision = updates.version(original)
        for step in range(3):
            version = f'{major}.{minor}.{revision+step}'
            versions.append(version)
            source = base/f'source-{step}'
            source.mkdir()
            for name, data in payload(ROOT/'world').items():
                dest = source/name;dest.parent.mkdir(parents=True, exist_ok=True);dest.write_bytes(data)
            meta = json.loads((source/'package.json').read_text(encoding='utf-8'))
            meta['version'] = version
            (source/'package.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            archive, files = pack(source, base/f'packages-{step}')
            archives[version], packages[version] = archive.read_bytes(), files

        class Registry(BaseHTTPRequestHandler):
            def do_GET(self):
                name = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
                if name == '/'+NAME:
                    data = {'name': NAME, 'dist-tags': {'latest': versions[-1]}, 'versions': {}}
                    for version in versions:
                        meta = json.loads(packages[version]['package.json'])
                        meta['dist'] = {'tarball': f'http://127.0.0.1:{self.server.server_port}/{version}.tgz',
                                        'integrity': 'sha512-'+base64.b64encode(hashlib.sha512(archives[version]).digest()).decode()}
                        data['versions'][version] = meta
                    body = json.dumps(data).encode()
                    content = 'application/json'
                elif name[1:-4] in archives and name.endswith('.tgz'):
                    body = archives[name[1:-4]];content = 'application/octet-stream'
                else:
                    self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type', content);self.send_header('Content-Length', str(len(body)));self.end_headers();self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        ext = base/'extensions';ext.mkdir()
        (ext/'package.json').write_text('{"private":true,"dependencies":{}}', encoding='utf-8')
        def market(version):
            done = subprocess.run([pnpm, 'add', '--ignore-workspace', '--ignore-scripts', '--registry',
                f'http://127.0.0.1:{server.server_port}', '--store-dir', str(base/'store'), NAME+'@'+version],
                cwd=ext, capture_output=True, text=True, encoding='utf-8', timeout=120)
            if done.returncode:
                raise RuntimeError('pnpm registry install failed: '+done.stderr[-1000:]+done.stdout[-1000:])
        def equal(version):
            installed = ext/'node_modules'/NAME
            if payload(installed) != packages[version]:
                raise AssertionError('Installed World differs from npm payload '+version)

        try:
            market(versions[0]);equal(versions[0])
            assert len(updates.world_targets(ext)) == 1  # A real marketplace install has no mirror.
            spec = importlib.util.spec_from_file_location('channel_installer', ROOT/'scripts/install_world.py')
            installer = importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
            # Install the exact current TGZ content from an offline bundle.
            bundle = base/'offline';(bundle/'scripts').mkdir(parents=True)
            for name,data in packages[versions[0]].items():
                dest=bundle/'world'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            bot = base/'bot';data = bot/'data/soft-voice';data.mkdir(parents=True)
            (bot/'config.json').write_text('{"worlds":{},"personal":"keep"}',encoding='utf-8')
            saved = {'speechEnabled':False,'config':{'volume':37,'syncBubbles':False,'deviceName':'Keep My GPU'}}
            (data/'settings.json').write_text(json.dumps(saved),encoding='utf-8')
            (data/'voices').mkdir();(data/'voices/my-voice.keep').write_bytes(b'keep-voice')
            runtime = base/'runtime';runtime.mkdir()
            (runtime/'model.gguf').write_bytes(b'keep-model')
            with patch.object(installer,'__file__',str(bundle/'scripts/install_world.py')), patch.object(installer.subprocess,'run'):
                installer.install(ext, bot, runtime)
            equal(versions[0])
            assert payload(ext/'local-soft-voice') == packages[versions[0]]
            assert json.loads((ext/'package.json').read_text())['dependencies'][NAME] == versions[0]
            assert json.loads((data/'settings.json').read_text()) == saved
            profile = (data/'runtime-profile.json').read_bytes()
            market(versions[1]);equal(versions[1])
            # An older offline bundle must connect its model without downgrading
            # an actually newer marketplace World (including the pnpm junction).
            with patch.object(installer,'__file__',str(bundle/'scripts/install_world.py')), patch.object(installer.subprocess,'run'):
                plan=installer.install(ext,bot,runtime)
            assert plan['action']=='skip'
            equal(versions[1])
            assert payload(ext/'local-soft-voice') == packages[versions[1]]

            # GitHub update covers the pnpm registry layout and its old offline mirror.
            site=runtime/'python/Lib/site-packages/coopanion_soft_voice';site.mkdir(parents=True)
            (site/'__init__.py').write_text("__version__='0.4.11'\n",encoding='utf-8')
            (runtime/'portable-manifest.json').write_text('{"version":"0.4.11"}')
            hashes={'dll':'a','model':'b','codec':'c'}
            (runtime/'native-runtime.json').write_text(json.dumps({'dllSha256':'a','speechOnly':{'hashes':{'model':'b','codec':'c'}}}))
            files={'world/'+name:content for name,content in packages[versions[2]].items()}
            files['python/coopanion_soft_voice/__init__.py']=b"__version__='0.5.0'\n"
            meta={'format':1,'version':'0.5.0','worldVersion':versions[2],'runtimeHashes':hashes,
                  'files':{name:hashlib.sha256(content).hexdigest() for name,content in files.items()}}
            archive=base/'update.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name,content in files.items():z.writestr(name,content)
                z.writestr('patch-manifest.json',json.dumps(meta))
            release={'format':1,'platform':'windows-x64','version':'0.5.0','worldVersion':versions[2],
                     'minimumVersion':'0.4.11','patch':{'file':'coopanion-voice-update-0.5.0.zip',
                     'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                     'url':f'https://github.com/{updates.REPO}/releases/download/v0.5.0/coopanion-voice-update-0.5.0.zip'}}
            with patch.object(updates,'emit'):
                updates.install_archive(runtime,archive,release,ext,verify=lambda:None)
            equal(versions[2])
            assert payload(ext/'local-soft-voice') == packages[versions[2]]
            assert json.loads((ext/'package.json').read_text())['dependencies'][NAME] == versions[2]
            assert (data/'runtime-profile.json').read_bytes() == profile
            assert json.loads((data/'settings.json').read_text()) == saved
            assert (data/'voices/my-voice.keep').read_bytes() == b'keep-voice'
            assert (runtime/'model.gguf').read_bytes() == b'keep-model'
            result={'ok':True,'registry':'isolated localhost, real pnpm installs','publicPublishPerformed':False,
                    'directions':['market to offline equal-version skip/repair','older offline keeps newer market','offline to newer market','market to GitHub update'],
                    'canonicalPayloadFiles':len(packages[versions[0]]),'exactPayloadMatch':True,
                    'preserved':['settings','voice files','runtime profile','model'],'gpuInferenceTested':False}
            Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    verify(p.parse_args().output)
