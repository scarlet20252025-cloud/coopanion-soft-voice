# 从干净 Windows 部署核显语音

本指南使用仓库文件及公开下载源。不需要作者提供 DLL、虚拟环境、模型目录或私有配置。保持安装目录不移动；以下默认使用仓库内 `.runtime-native`。

建议仓库和 Runtime 使用英文路径，避免上游 Windows 原生文件接口对非 ASCII 路径的兼容问题。

## 1. 前提

- Windows 10/11 x64；安装 [Python 3.10](https://www.python.org/downloads/windows/) x64 和 [Git for Windows](https://git-scm.com/downloads/win)，新开 PowerShell 验证 `py -3.10 --version`、`git --version`。
- 安装显卡厂商驱动并启用核显，需要系统 `vulkan-1.dll`。只开启独显的模式不适用。当前实测核显名为 `AMD Radeon(TM) Graphics`，其他硬件需验证。
- 至少 8 GB 可用磁盘，建议 16 GB 以上 RAM，启动语音前至少 4 GiB 空闲 RAM。首次编译可能需要几分钟或更久。
- 网络可访问 GitHub、PyPI、Google Storage、Hugging Face。无需语音 API 密钥。若需代理，可设置当前终端的 `HTTPS_PROXY`/`HTTP_PROXY`；脚本不会改系统代理。

## 2. 安装

```powershell
git clone https://github.com/scarlet20252025-cloud/coopanion-soft-voice.git
cd coopanion-soft-voice
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-native.ps1
```

若设备名不同，追加 `-DeviceName '实际 Vulkan 核显名称'`。运行时按名称及集成显卡类型匹配，无法唯一匹配会停止，不回退独显。设备管理器名称可作线索，以 Vulkan 枚举为准。

脚本支持 `-Python 'python.exe的完整路径'`（3.10 x64）、`-Runtime '自选目录'`、`-Cache '下载缓存目录'`。自选 Runtime 时，后续命令的 `.runtime-native` 一并替换。核显安装使用独立 venv，不安装 Torch。

如果 PyPI 下载失败，可仅在当前终端选择 HTTPS 镜像后重跑（不会关闭证书校验）：

```powershell
$env:PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-native.ps1
```

| 内容 | 固定版本 |
|---|---|
| qwentts.cpp | `51512f129a7419567f4b8abfb06801451789b8f1` |
| ggml 子模块 | `2eddaf94a8cdbbf1c30017d28313cd661a9da543` |
| LLVM MinGW | 20261006 UCRT x64 |
| CMake / Ninja | 4.4.4 / 1.13.2 |
| Vulkan / SPIRV Headers | 1.4.328 / vulkan-sdk-1.4.328.1 |
| glslc | Google shaderc Windows 20261001 |
| Q8 模型 | Serveurperso/Qwen3-TTS-GGUF `b7ee2e8c7459c3bea99da23e3d178125a7d1713c` |

工具链 URL 和 SHA256 在 [setup_native.py](../scripts/setup_native.py)，权重信息在 [manifest.json](../evidence/2026-10-12-native/manifest.json)。下载先校验后使用；正确缓存会复用。Vulkan import library 根据本机驱动导出生成，DLL 在本机编译。配置自动生成，无需手填作者路径。

成功末尾应显示 `backend: native-igpu`、正确设备和 `voice: soft-child-design-2`。这一步检查资源和输出设备，下一步实际合成。

## 3. 试听

```powershell
.runtime-native\venv\Scripts\python.exe scripts/preview_native.py --output preview.wav
```

手动打开 `preview.wav`。可加 `--text '你在吗？我来陪你啦。'`，单次不超过 60 字。试听使用正式 NativeEngine、完整 ICL、Q8、固定种子与预热，不自动播放或修改桌宠。固定音源随软件包分发并校验 SHA256，无需另找音源。

## 4. 接入 Coopanion

1. 安装 [Coopanion](https://github.com/Pal-AI-Lab/Coopanion)，完成桌宠及聊天模型配置。已验证 0.1.22，新版需验证兼容。
2. 在扩展管理安装 `cortico-world-cosyvoice-tts@0.1.11`，无需初始化原来的 CosyVoice 环境。
3. 退出 Coopanion。扩展页显示共享扩展目录，插件位于其 `node_modules/cortico-world-cosyvoice-tts`；pnpm 也可用 `.pnpm/cortico-world-cosyvoice-tts@0.1.11/node_modules/cortico-world-cosyvoice-tts`。选择含 package.json、src、runtime 的那一层。
4. 在仓库根目录执行：

```powershell
$plugin = Read-Host '粘贴插件目录'
.runtime-native\venv\Scripts\python.exe scripts/install_plugin.py --plugin "$plugin" --runtime .runtime-native --mode igpu
```

保留打印的备份目录。默认启用语音；只安装时加 `--keep-disabled`。重启 Coopanion 后等待 ready（加载预热数秒至十几秒），再聊天。

检查配置，不加载模型、不改变开关：

```powershell
.runtime-native\venv\Scripts\python.exe scripts/voice_mode.py --plugin "$plugin"
```

应有 `mode: igpu`、`speechEnabled: true`。实际运行状态以桌宠语音面板为准。

## 5. 停用、回滚与升级

在 TTS 配置页关闭语音可释放 worker，保留模型。回滚时退出桌宠：

```powershell
$backup = Read-Host '安装器打印的备份目录'
.runtime-native\venv\Scripts\python.exe scripts/install_plugin.py --restore "$backup"
```

重启生效。升级本项目时退出桌宠，`git pull` 后重跑 setup-native.ps1 和插件安装命令。社区插件升级可能覆盖补丁；遇到不支持的版本不要绕过检查。不要把 venv 直接复制到另一台电脑，应重新运行安装。

## 排查

| 问题 | 处理 |
|---|---|
| 无 Python 3.10 | 安装 3.10 x64 或传 `-Python`；3.14 不适用 |
| 下载超时 | 检查网络/代理后重跑；未完成文件不视为成功 |
| SHA256 不匹配 | 检查下载源，不要改期望哈希绕过 |
| 缺 Vulkan / 核显不匹配 | 安装厂商驱动、开启核显、检查设备名 |
| 空闲内存不足 | 关闭不需要的程序再启用语音，不会改用游戏显卡 |
| ready 但没声音 | 检查 TTS 开关、音量、输出设备，确认 bot 使用桌宠说话工具 |
| 新聊天换声 | 检查 mode、其他 TTS 插件，以及升级是否覆盖补丁 |
| 构建中断 | 同目录重跑；自行改动原生源码后建议换新 Runtime 重建 |

初次部署联网，安装后语音推理可离线。聊天模型是否联网取决于 Coopanion 配置，无需作者电脑在线。
