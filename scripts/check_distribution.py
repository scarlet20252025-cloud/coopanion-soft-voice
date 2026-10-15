"""Check that an sdist actually carries the files needed for native deployment."""
from pathlib import Path
import tarfile
import zipfile
import json

root = Path(__file__).resolve().parents[1]
archive = max((root/'dist').glob('*.tar.gz'), key=lambda p: p.stat().st_mtime)
with tarfile.open(archive) as tar:
    names = {'/'.join(n.split('/')[1:]) for n in tar.getnames()}
required = {
    'docs/PERFORMANCE_0.5.2.md','scripts/benchmark_speech_recovery.py',
    'world/dist/console-0.4.2.js','world/dist/console-0.4.2.css','src/coopanion_soft_voice/pcm_cache.py',
    'native/voice_worker_trial.cpp','scripts/build_native_worker_trial.ps1','docs/NATIVE_WORKER_EVALUATION.md',
    'world/dist/console-0.4.1.js','world/dist/console-0.4.1.css',
    'src/coopanion_soft_voice/reports.py','src/coopanion_soft_voice/issue_reporting.py','world/src/reports.js',
    'src/coopanion_soft_voice/world_package.py','scripts/verify_install_channels.py','docs/INSTALL_CHANNELS.md',
    'evidence/2026-10-15-vram/qwentts-progressive-kv.patch', 'scripts/benchmark_vram.py', 'src/coopanion_soft_voice/gpu_memory.py',
    'docs/DIAGNOSTICS.md','scripts/build_diagnostics.py','scripts/collect-diagnostics.ps1','scripts/report_issue.py','src/coopanion_soft_voice/diagnostics.py','collect-diagnostics.cmd',
    'AGENTS.md', 'CHANGELOG.md', 'docs/AI_BUG_REPORTS.md', 'docs/PLAYBACK_AND_UPDATES.md', 'scripts/build_update.py', 'src/coopanion_soft_voice/updates.py', 'docs/AI_DEPLOYMENT.md', 'scripts/deploy.ps1',
    'scripts/prepare_speech_profile.py', 'scripts/verify_deployment.py',
    'portable-release.json', 'docs/PORTABLE_INSTALL.md', 'scripts/deploy-source.ps1',
    'scripts/install-portable.ps1', 'scripts/activate_portable.py', 'scripts/build_portable.py',
    'world/dist/console-0.4.0.js', 'world/dist/console-0.4.0.css', 'world/src/updates.js', 'world/src/helpers.js', 'world/src/install_bubble_bridge.py',
    'evidence/2026-10-14-text-rows/qwentts-text-rows.patch',
    'src/coopanion_soft_voice/native_capabilities.py',
    'scripts/setup-native.ps1', 'scripts/setup_native.py', 'scripts/build_native_windows.ps1',
    'scripts/preview_native.py', 'scripts/install_plugin.py', 'scripts/voice_mode.py',
    'requirements-native.txt', 'docs/DEPLOY_NATIVE.md',
    'evidence/2026-10-12-native/manifest.json', 'evidence/2026-10-12-native/qwentts-experiment.patch',
    'src/coopanion_soft_voice/assets/soft-child-design-2.wav',
    'scripts/install_world.py', 'docs/VOICE_PACKS.md', 'docs/CORTICO_COMPATIBILITY.md',
    'world/package.json', 'world/src/world.js', 'world/dist/console-0.3.6.js', 'world/dist/console-0.3.6.css',
    'src/coopanion_soft_voice/memory_policy.py', 'src/coopanion_soft_voice/memory_metrics.py',
    'evidence/2026-10-12-native/qwentts-kv-context.patch',
    'evidence/2026-10-14-compact-native/qwentts-compact-graphs.patch',
}
world = json.loads((root/'world/package.json').read_text(encoding='utf-8'))
required.update('world/'+world['cortico'][key] for key in ('consoleClient','consoleStyle'))
assert required <= names, sorted(required - names)
wheel = max((root/'dist').glob('*.whl'), key=lambda p: p.stat().st_mtime)
with zipfile.ZipFile(wheel) as z:
    assert 'coopanion_soft_voice/assets/soft-child-design-2.wav' in z.namelist()
    assert 'coopanion_soft_voice/voice_pack.py' in z.namelist()
print('Native deployment sdist and wheel contents verified')
