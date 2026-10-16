# 轻核语音 · Qwen3-TTS 超轻量高速语音引擎 · Coopanion


完整包约 **1.09 GiB**（0.5.2 实测）：主模型解压后约 **924 MiB**，音频解码模型约 **192 MiB**，另含运行库、播放器和扩展。**0.6B 是参数规模，不是几十 MB 的模型**；精简运行组件、推理缓存与模型权重是不同的体积指标。已有兼容模型可只下载代码更新，无需重复下载模型。
作者：**Asryto** · 稳定语音引擎 **0.5.4** / World **0.4.8**（0.5.5 修复纯独显机器部署，正在发布流程中）

当前工程状态与验收边界见 [工程进度](docs/PROJECT_STATUS.md)。Intel 用户反馈慢速时，可下载 [双击测试工具](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/download/diagnostic-intel-v1.0.0/QingHe-Intel-Diagnostic-1.0.0.zip)，解压后运行 `START.cmd`，结束后回传自动生成的报告 ZIP。工具不替换稳定版，Intel 提速仍待实机验收。

0.5.0 原生模型已验证本机 AMD 核显与 RTX 4050；0.5.1 的缓存和线程池改进另经 RTX 4050 实测。Intel UHD 提速、其他显卡和能效提升仍在 [验证与优化计划](docs/OPTIMIZATION_PLAN.md) 中，不作为已通过承诺。

Windows Coopanion 的独立 Vulkan 语音扩展。保留已确认的 `soft-child-design-2`，支持流式播放、独立气泡同步开关、低功耗休眠、延迟图表、模型部署检测和 ZIP 音色库。主页明确区分未部署、加载、已连接、休眠和内存不足，提供魔搭优先的一键部署、备用源和离线 ZIP 导入；失败时才显示手动部署指南。

## 最简安装

新增可控重复语句缓存和线程池精简；保留慢设备连续播放、核显/独显选择、右上角更新提示与一键主动更新，详见 [更新记录](CHANGELOG.md)。原音色与采样参数保持不变。

**[不依赖扩展市场的安装教程](docs/INSTALL_WITHOUT_MARKET.md)**：完整包自动安装 World，不需要 npm 账号或市场安装。

1. 从 [GitHub Releases 下载完整 Windows 安装包](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest)，解压到英文路径，例如 `D:\CoopanionVoice`。
2. 双击 **`install.cmd`**。自动寻找正在运行的桌宠、快捷方式、安装记录与常见目录；找不到或有多个副本时再选择路径。
3. 安装器校验模型、执行真实合成和静音播放测试，接入 World 并重启桌宠。进入 **轻核语音 · Qwen3-TTS 超轻量高速语音引擎** 即可使用。

默认自动选择核显。安装时可用 `-DeviceName 'Vulkan 设备名称'` 明确指定独显；面板中“检测设备 → 切换设备”可在空闲时重载模型，不重启桌宠。独显与游戏共享显存，错误不会导致自动切换到别的 GPU。

生成偏慢时，默认先生成整句再连续播放；这能消除合成欠载造成的间歇静音，但不代表推理变快。设备表现、RTF 和断流需看实际验收：[播放与设备说明](docs/PLAYBACK_AND_UPDATES.md)。

排错 AI 在用户已授权报障时应按 [AI Issue 规范](docs/AI_BUG_REPORTS.md) 自动提交脱敏问题。

性能或错误反馈可用 [诊断包与日志采集](docs/DIAGNOSTICS.md)。AI 无法提交时生成含日志、分析和 Issue 草稿的 ZIP 交回作者。

**完整包自带固定音色精简版 Qwen3-TTS 0.6B Base Q8、音频解码模型、Vulkan DLL、Python 3.12 和播放器依赖。无需安装 Python、Git、Node、PyTorch、CUDA 或编译工具，无需语音 API key。** 解压目录就是运行目录，请保留。

仍需要 Windows 10/11 x64、支持 Vulkan 的显卡及厂商驱动、至少 **3 GiB 系统可用内存**和约 **4 GB 可用磁盘**。桌宠应先安装并初始化一次；本包不提供桌宠角色、聊天模型账号或账号额度。默认使用核显；独显须明确选择，不自动切换设备或默认声音。其他硬件需验证驱动与实际性能。

详细步骤、迁移及排错见 [便携安装指南](docs/PORTABLE_INSTALL.md)。作者和上游许可证均保留，见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 让 AI 完整部署

把本仓库链接交给 AI，先读 [AGENTS.md](AGENTS.md) 和 [AI 部署指南](docs/AI_DEPLOYMENT.md)。仓库默认入口自动下载并校验同一个免编译包：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy.ps1
```

可指定 `-CoopanionRoot '你的桌宠目录'`、`-Runtime '英文安装路径'`、`-BotId 'Bot目录名'`；`-RuntimeOnly` 仅验证语音，`-NoLaunch` 安装后不打开桌宠。包内安装器也支持这些操作。多块显卡或独显用 `-DeviceName 'Vulkan设备名称'`。

[源码重建](docs/DEPLOY_NATIVE.md) 是开发者备用路线，入口 `scripts/deploy-source.ps1`。不再作为普通用户默认安装步骤。模型、源码、补丁及固定下载校验公开；不依赖作者电脑的虚拟环境、模型路径或 DLL。单个 Python wheel 包含代码和音色，但不包含全部模型；**完整离线部署请使用 Release ZIP**。

## 功能与证据

- [独立扩展与官方 Cortico 接口](docs/STANDALONE_WORLD.md)：提示词按官方 `envPrompt` 注入，让桌宠知道真实语音状态。气泡同步首次默认启用，可独立关闭并记住选择。
- [音色制作与 ZIP 导入](docs/VOICE_PACKS.md)：当前精简模型锁定已确认音色；自定义音色需完整运行时。未来默认音色标为“待更新”。
- [内存优化](docs/MEMORY_OPTIMIZATION.md)、[固定音色精简模型](docs/SPEECH_ONLY.md)：预计算参考特征、KV 1024、紧凑计算图、文字词表按需加载。低功耗模式在空闲时释放模型，下一句自动唤醒；不改变运行中模型需求。
- [长回复音色稳定性](docs/VOICE_STABILITY.md)：自然句界最多 32 字，逐段锁定完整参考特征；不换模型精度、种子或声线，不回退默认声音。
- [核显及 CS2 验证记录](docs/NATIVE_TRIAL.md)：先前暖机首次设备回调约 1.18–1.43 秒；短时共存通过，不代表所有游戏和负载的性能保证。

历史文字词表优化减少约 248–316 MiB **私有提交内存**，7 条测试 PCM 与原版一致。这不是总显存指标。新便携包的验证记录见 `evidence/2026-10-14-portable/`；无真人重新试听的测试不得宣称新的听感验收。

源码构建：`python -m build`。Windows CI 检查 Python/World 测试及打包内容；原生构建从固定源码应用补丁。无 GPU 的 CI 不能代替真实核显合成。

新版增加最多 4 MiB 的进程内重复语句缓存，并精简 NumPy 的空闲线程池。只降低对应开销，不宣称新句推理或物理 RAM 成比例改善。[社区 C++ 方案与原生工作进程评估](docs/NATIVE_WORKER_EVALUATION.md)记录已验证结果、失败样本和后续流式验收计划。
