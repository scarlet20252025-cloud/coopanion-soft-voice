# 轻量化本地语音引擎 · Asryto

**无需扩展市场或 npm 账号。完整 ZIP 已包含扩展、模型和运行环境。**

首次安装请看 [不依赖扩展市场的详细步骤与排错指南](INSTALL_WITHOUT_MARKET.md)。

## 最简安装

1. 下载 [完整 Windows 便携 ZIP](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/download/v0.4.11/coopanion-local-voice-0.4.11-windows-x64.zip)，解压到英文路径，例如 `D:\CoopanionVoice`。
2. 双击 `install.cmd`，自动识别 Coopanion 的运行路径、快捷方式、安装记录和常见目录；仅找不到或存在多个副本时要求选择目录。若桌宠正在运行，已验证版本会尝试正常退出后安装。
3. 安装器校验模型、实际生成一段语音并测试静音播放，安装独立 World 后打开桌宠。进入“轻量化本地语音引擎”即可使用。

不需要另外安装 Python、Git、Node、PyTorch、CUDA 或编译工具，不需要语音 API key。Qwen3-TTS 0.6B Base Q8 固定音色精简模型、Vulkan 引擎、Python 3.12、播放器依赖与 `soft-child-design-2` 都在包内。首次气泡同步默认开启，可单独关闭，选择会保留。

仍需要 Windows 10/11 x64、可用的 Vulkan 核显和厂商驱动，以及启动前至少 3 GiB 系统可用内存。安装包不含桌宠程序、角色素材或聊天模型账号；桌宠应先初始化一次，聊天模型使用自己的配置。不要把进程内存指标当成总显存占用。

保留解压目录；模型与 Python 在其中运行。搬到其他英文路径后再运行安装器即可重新生成本机路径配置。不会注册开机自启，不改系统 PATH，不强制终止游戏。当前气泡显示桥适配官方桌宠包 0.1.4，未知版本会提示。

AI 或终端也可执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install-portable.ps1 -CoopanionRoot '你的桌宠目录'
```

仅验收运行包用 `-RuntimeOnly`；安装后不打开桌宠用 `-NoLaunch`；多块核显时用 `-DeviceName '设备名称'`；其他 Bot 用 `-BotId '目录名'`。验证记录在 `verification/deployment-check.json`，故障详情在 `installation.log`。

作者：**Asryto**。原生引擎、模型、Python 和其他依赖保留各自许可证，见 `THIRD_PARTY_NOTICES.md` 与 `licenses`。本包不包含作者账号或个人聊天记录。
