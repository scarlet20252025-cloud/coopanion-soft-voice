"""Build the redistributable diagnostic kit without models, credentials or local paths."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ('start_gpu_diagnostic.ps1', 'find-coopanion.ps1', 'run_gpu_diagnostic.py',
           'benchmark_intel_issue13.py', 'benchmark_speech_recovery.py')


def build(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = 'QingHe-Intel-Diagnostic/'
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(prefix+'START.cmd', '@echo off\r\nchcp 65001 >nul\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\start_gpu_diagnostic.ps1"\r\n')
        for name in SCRIPTS:
            file = ROOT / 'scripts' / name
            text = file.read_text(encoding='utf-8-sig')
            # Windows PowerShell 5.1 requires a BOM for Chinese source text.
            z.writestr(prefix+'scripts/'+name, text.encode('utf-8-sig' if name.endswith('.ps1') else 'utf-8'))
        package = ROOT / 'src/coopanion_soft_voice'
        for file in sorted(package.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts and (
                file.suffix in ('.py', '.json', '.txt') or file.name == 'soft-child-design-2.wav'):
                z.write(file, prefix+file.relative_to(ROOT).as_posix())
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
            z.write(ROOT / name, prefix+name)
        z.write(ROOT / 'docs/INTEL_DIAGNOSTIC_KIT.md', prefix+'README.md')
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix+'.sha256').write_text(digest+'  '+destination.name+'\n', encoding='ascii')
    return {'file': destination.name, 'bytes': destination.stat().st_size, 'sha256': digest}


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    print(json.dumps(build(parser.parse_args().output)))
