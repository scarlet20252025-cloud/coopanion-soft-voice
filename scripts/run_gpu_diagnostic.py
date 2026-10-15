"""Double-click kit backend; reuse installed Python/model in an isolated profile."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from coopanion_soft_voice.diagnostics import redact, static_info
from coopanion_soft_voice.native_engine import vulkan_devices


def choose_device(devices, requested=None):
    candidates = [d for d in devices if d['kind'] == 'integrated']
    if requested:
        matches = [d for d in candidates if d['name'] == requested]
    else:
        matches = [d for d in candidates if d.get('vendorId') == 0x8086]
    if len(matches) != 1:
        raise RuntimeError('无法唯一识别 Intel 核显；不会自动改用独显。请将本报告发给作者。'
                           ' AI 可通过 --device 明确指定检测到的核显。')
    return matches[0]['name']


def isolated_profile(runtime, destination):
    runtime = Path(runtime).resolve()
    cfg = json.loads((runtime / 'native-runtime.json').read_text(encoding='utf-8-sig'))
    for key in ('dll', 'model', 'codec'):
        file = Path(cfg[key])
        if not file.is_absolute():
            file = runtime / file
        if not file.is_file():
            raise RuntimeError('运行时文件缺失：'+key+'；请在扩展中完成部署后重试。')
        cfg[key] = str(file.resolve())
    cfg['dllDirectories'] = [str((runtime / p).resolve()) for p in cfg.get('dllDirectories', [])]
    destination.mkdir()
    (destination / 'native-runtime.json').write_text(json.dumps(cfg), encoding='utf-8')
    if cfg.get('speechOnly'):
        shutil.copyfile(runtime / 'voice-features.json', destination / 'voice-features.json')
    return cfg['dllSha256']


def scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def pack_report(folder, archive, status):
    # Allowlist generated data. Never include runtime profiles, audio or user config.
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('status.json', json.dumps(scrub(status), ensure_ascii=False, indent=2))
        for p in sorted((folder / 'trials').rglob('*')):
            if not p.is_file():
                continue
            relative = p.relative_to(folder).as_posix()
            if p.name in ('comparison.json', 'report.json'):
                try:
                    data = scrub(json.loads(p.read_text(encoding='utf-8')))
                    z.writestr(relative, json.dumps(data, ensure_ascii=False, indent=2))
                except (OSError, ValueError):
                    z.writestr(relative+'.error.txt', 'Report incomplete; trial interrupted.')
            elif p.suffix == '.log':
                text = p.read_text(encoding='utf-8', errors='replace')
                z.writestr(relative, '\n'.join(redact(line) for line in text.splitlines()))
        z.writestr('README.txt', '作者 Asryto。此包为本机合成对照日志，不包含模型、音频、聊天或账号配置。\n'
                   '首块时间不是扬声器出声；实验结果不能自动判定为可发布。\n'
                   '关联 https://github.com/scarlet20252025-cloud/coopanion-soft-voice/issues/13\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runtime', required=True)
    p.add_argument('--device', help='AI/manual: exact integrated GPU name; default auto-detect Intel')
    p.add_argument('--output', help='New result directory; default kit/reports/timestamp')
    p.add_argument('--preflight-only', action='store_true', help='Detection and packaging only; no synthesis')
    a = p.parse_args()
    folder = Path(a.output).resolve() if a.output else ROOT / 'reports' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder.mkdir(parents=True, exist_ok=False)
    archive = folder.with_suffix('.zip')
    status = {'toolVersion': '1.0.0', 'issue': 13, 'success': False,
              'synthesisAttempted': False, 'installedConfigurationModified': False,
              'playbackValidated': False, 'hardware': static_info()}
    from coopanion_soft_voice import __version__
    status['testHarnessEngineVersion'] = __version__
    try:
        status['installedRuntimeVersion'] = json.loads((Path(a.runtime) / 'portable-manifest.json').read_text(encoding='utf-8-sig')).get('version')
    except (OSError, ValueError):
        status['installedRuntimeVersion'] = None
    exit_code = 1
    try:
        print('正在检测 Vulkan 核显与语音运行时……', flush=True)
        devices = vulkan_devices()
        status['devices'] = devices
        device = choose_device(devices, a.device)
        status['selectedDevice'] = device
        status['nativeSha256'] = isolated_profile(a.runtime, folder / 'isolated-runtime')
        print('本次测试核显：'+device+'（不改变桌宠设备设置）', flush=True)
        if a.preflight_only:
            status['preflightOnly'] = True
        else:
            print('共四组测试，每组最多 15 分钟。只生成固定测试句，不播放声音。Ctrl+C 可取消并保留报告。', flush=True)
            status['synthesisAttempted'] = True
            command = [sys.executable, str(ROOT / 'scripts/benchmark_intel_issue13.py'),
                       '--runtime', str(folder / 'isolated-runtime'), '--device', device,
                       '--output', str(folder / 'trials')]
            subprocess.run(command, check=True)
        status['success'] = True
        exit_code = 0
    except KeyboardInterrupt:
        status['error'] = '用户取消，已保留完成的测试。'
    except Exception as exc:
        status['error'] = redact(str(exc))
        print('未完成：'+status['error'], flush=True)
    finally:
        pack_report(folder, archive, status)
        print('\n'+('测试完成。' if status['success'] else '测试未完成，故障信息已打包。'), flush=True)
        print('请把这个 ZIP 发给作者：\n'+str(archive), flush=True)
        print('未自动上传。测试音频仅保留本地；可删除整个 reports 目录。', flush=True)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
