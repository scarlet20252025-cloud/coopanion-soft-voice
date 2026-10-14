"""Pinned Windows native build; no dependency on the author's machine or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REVISION = '51512f129a7419567f4b8abfb06801451789b8f1'
DOWNLOADS = {
    'llvm-mingw.zip': (
        'https://github.com/mstorsjo/llvm-mingw/releases/download/20261006/llvm-mingw-20261006-ucrt-x86_64.zip',
        '317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a'),
    'vulkan-headers.zip': (
        'https://github.com/KhronosGroup/Vulkan-Headers/archive/refs/tags/v1.4.328.zip',
        '75fe4d82d41381229ea7dea2892e3344f500fd5de62e8994f79f4979f432a261'),
    'spirv-headers.zip': (
        'https://github.com/KhronosGroup/SPIRV-Headers/archive/refs/tags/vulkan-sdk-1.4.328.1.zip',
        'ddba9a5c22491ed9d6d7f37830628d0230cbadc58dd723755ae1bb49fbbfab58'),
    'shaderc.zip': (
        'https://storage.googleapis.com/shaderc/artifacts/prod/graphics_shader_compiler/shaderc/windows-vs2022-amd64-release/continuous/48/20261001-205140/install.zip',
        '62615a97a79a708b07c4034b8d1ddf0f369ce0b91778a1f380256f77b1301182'),
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(data)
    return h.hexdigest()


def download(url, dest, digest):
    dest = Path(dest)
    if dest.exists() and sha256(dest) == digest:
        print('Verified cached:', dest.name, flush=True)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.partial')
    print('Downloading:', url, flush=True)
    with urllib.request.urlopen(url, timeout=120) as response, temp.open('wb') as out:
        shutil.copyfileobj(response, out, 1024**2)
    if sha256(temp) != digest:
        temp.unlink()
        raise ValueError('Checksum mismatch: ' + dest.name)
    os.replace(temp, dest)
    return dest


def extract(archive, target):
    target = Path(target).resolve()
    marker = target / '.archive-sha256'
    digest = sha256(archive)
    if marker.exists() and marker.read_text() == digest:
        return
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if not (target / entry.filename).resolve().is_relative_to(target):
                raise ValueError('Unsafe archive member')
        z.extractall(target)
    marker.write_text(digest)


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def setup(runtime, cache, device_name, build_only=False):
    if sys.platform != 'win32':
        raise RuntimeError('Windows x64 is required')
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    cache = Path(cache).resolve() if cache else runtime / 'downloads'
    native = runtime / 'native'
    native.mkdir(exist_ok=True)
    for name, (url, digest) in DOWNLOADS.items():
        extract(download(url, cache / name, digest), native / name.removesuffix('.zip'))
    toolchain = native / 'llvm-mingw/llvm-mingw-20261006-ucrt-x86_64/bin'
    vulkan = native / 'vulkan-headers/Vulkan-Headers-1.4.328'
    spirv = native / 'spirv-headers/SPIRV-Headers-vulkan-sdk-1.4.328.1'
    glslc = native / 'shaderc/install/bin/glslc.exe'
    scripts = Path(sys.executable).parent
    cmake = scripts / 'cmake.exe'
    ninja = scripts / 'ninja.exe'
    if not cmake.exists() or not ninja.exists():
        raise RuntimeError('Run setup-native.ps1 to install CMake and Ninja first')
    # Build the import library from the installed Vulkan loader; no SDK installer needed.
    loader = Path(os.environ['SystemRoot']) / 'System32/vulkan-1.dll'
    if not loader.is_file() and not build_only:
        raise RuntimeError('Vulkan loader missing. Install the GPU vendor driver first.')
    if loader.is_file():
        exports = subprocess.check_output([str(toolchain/'llvm-readobj.exe'), '--coff-exports', str(loader)], text=True)
        names = re.findall(r'^\s*Name: (vk\w+)\s*$', exports, re.MULTILINE)
    else:
        # CI builds on machines without a GPU driver; it must not claim runtime readiness.
        header = (vulkan/'include/vulkan/vulkan_core.h').read_text(encoding='utf-8')
        names = sorted(set(re.findall(r'VKAPI_CALL\s+(vk\w+)\s*\(', header)))
    if 'vkGetInstanceProcAddr' not in names:
        raise RuntimeError('Vulkan loader exports unavailable')
    definition = native / 'vulkan.def'
    definition.write_text('LIBRARY vulkan-1.dll\nEXPORTS\n' + '\n'.join(names) + '\n', encoding='ascii')
    library = native / 'libvulkan-1.a'
    run(toolchain/'llvm-dlltool.exe', '-m', 'i386:x86-64', '-d', definition, '-l', library)
    source = native / 'qwentts'
    if not source.exists():
        run('git', 'init', source)
        run('git', '-C', source, 'remote', 'add', 'origin', 'https://github.com/ServeurpersoCom/qwentts.cpp.git')
    head = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True, capture_output=True)
    if head.returncode:
        origin = subprocess.check_output(['git', '-C', str(source), 'remote', 'get-url', 'origin'], text=True).strip()
        if origin != 'https://github.com/ServeurpersoCom/qwentts.cpp.git':
            raise RuntimeError('Unexpected source remote; use a new runtime directory')
        run('git', '-C', source, 'fetch', '--depth', '1', 'origin', REVISION)
        run('git', '-C', source, 'checkout', '--detach', REVISION)
    elif head.stdout.strip() != REVISION:
        raise RuntimeError('Existing source has an unexpected revision; use a new runtime directory')
    run('git', '-C', source, 'submodule', 'update', '--init', '--recursive', '--depth', '1')
    prefix = native / 'spirv-sdk'
    run(cmake, '-S', spirv, '-B', native/'spirv-build', '-G', 'Ninja',
        '-DCMAKE_MAKE_PROGRAM=' + str(ninja), '-DCMAKE_INSTALL_PREFIX=' + str(prefix),
        '-DCMAKE_C_COMPILER=' + str(toolchain/'x86_64-w64-mingw32-clang.exe'),
        '-DCMAKE_CXX_COMPILER=' + str(toolchain/'x86_64-w64-mingw32-clang++.exe'),
        '-DSPIRV_HEADERS_ENABLE_TESTS=OFF')
    run(cmake, '--install', native/'spirv-build')
    run('powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ROOT/'scripts/build_native_windows.ps1',
        '-Source', source, '-Toolchain', toolchain, '-CMake', cmake, '-NinjaDirectory', scripts,
        '-VulkanHeaders', vulkan/'include', '-VulkanLibrary', library, '-Glslc', glslc, '-SpirvPrefix', prefix)
    dll = source/'build-vulkan/libqwen.dll'
    if build_only:
        print('Build-only completed; models not downloaded and runtime not activated:', dll)
        return
    manifest = json.loads((ROOT/'evidence/2026-10-12-native/manifest.json').read_text())
    paths = {}
    for key, name in [('model', 'qwen-talker-0.6b-base-Q8_0.gguf'), ('codec', 'qwen-tokenizer-12hz-Q8_0.gguf')]:
        url = f"https://huggingface.co/{manifest['model_repo']}/resolve/{manifest['model_revision']}/{name}"
        paths[key] = str(download(url, runtime/'models'/name, manifest['files'][name]['sha256']))
    config = dict(paths, dll=str(dll), dllSha256=sha256(dll), dllDirectories=[str(toolchain)], deviceName=device_name, kvContext=1024, compactGraphs=True)
    # Validate before replacing a previously working configuration.
    from coopanion_soft_voice.native_engine import integrated_device
    integrated_device(device_name)
    path = runtime/'native-runtime.json'
    if path.exists():
        shutil.copy2(path, runtime/'native-runtime.previous.json')
    temp = runtime/'native-runtime.json.partial'
    temp.write_text(json.dumps(config, indent=2), encoding='utf-8')
    os.replace(temp, path)
    run(sys.executable, '-m', 'coopanion_soft_voice.cli', '--runtime', runtime, 'doctor', '--mode', 'igpu')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True)
    p.add_argument('--cache')
    p.add_argument('--device-name', default='AMD Radeon(TM) Graphics')
    p.add_argument('--build-only', action='store_true')
    a = p.parse_args()
    setup(a.runtime, a.cache, a.device_name, a.build_only)
