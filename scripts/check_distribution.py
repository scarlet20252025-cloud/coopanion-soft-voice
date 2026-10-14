"""Check that an sdist actually carries the files needed for native deployment."""
from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
archive = max((root/'dist').glob('*.tar.gz'), key=lambda p: p.stat().st_mtime)
with tarfile.open(archive) as tar:
    names = {'/'.join(n.split('/')[1:]) for n in tar.getnames()}
required = {
    'scripts/setup-native.ps1', 'scripts/setup_native.py', 'scripts/build_native_windows.ps1',
    'scripts/preview_native.py', 'scripts/install_plugin.py', 'scripts/voice_mode.py',
    'requirements-native.txt', 'docs/DEPLOY_NATIVE.md',
    'evidence/2026-10-12-native/manifest.json', 'evidence/2026-10-12-native/qwentts-experiment.patch',
    'src/coopanion_soft_voice/assets/soft-child-design-2.wav',
    'scripts/install_world.py', 'docs/VOICE_PACKS.md', 'docs/CORTICO_COMPATIBILITY.md',
    'world/package.json', 'world/src/world.js', 'world/dist/console-0.3.4.js', 'world/dist/console-0.3.4.css',
    'src/coopanion_soft_voice/memory_policy.py', 'src/coopanion_soft_voice/memory_metrics.py',
    'evidence/2026-10-12-native/qwentts-kv-context.patch',
    'evidence/2026-10-14-compact-native/qwentts-compact-graphs.patch',
}
assert required <= names, sorted(required - names)
wheel = max((root/'dist').glob('*.whl'), key=lambda p: p.stat().st_mtime)
with zipfile.ZipFile(wheel) as z:
    assert 'coopanion_soft_voice/assets/soft-child-design-2.wav' in z.namelist()
    assert 'coopanion_soft_voice/voice_pack.py' in z.namelist()
print('Native deployment sdist and wheel contents verified')
