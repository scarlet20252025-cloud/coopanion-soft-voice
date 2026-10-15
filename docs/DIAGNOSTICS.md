# 收集诊断与交回作者

作者 **Asryto**。反馈仓库：[coopanion-soft-voice](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/issues)。诊断采集不加载模型。命令行默认仅生成本地 ZIP；扩展内可单独开启自动提交脱敏 Issue。

## 扩展内直接查看与导出

Intel UHD 合成过慢需要主动 A/B 对照时，使用 [双击诊断工具](INTEL_DIAGNOSTIC_KIT.md)。它会实际加载模型并生成固定测试句，区别于本页的被动日志采集。下载、解压、双击 START.cmd 即可自动发现运行时、测试并打包；异常也会留报告，用户/AI 不必手填长命令。

打开“轻核语音 · Qwen3-TTS 超轻量高速语音引擎 → 日志与诊断”：

- **立即生成报告**：保存当前设备、驱动、内存、工作进程、启动阶段、错误类型与最近播放指标。
- **监测 60 秒**：点击后正常使用语音，记录这一分钟的进程 RAM/CPU、独立/共享 GPU 内存和系统 GPU 负载。只观察，不自动发起合成。
- **查看报告 / 导出 ZIP**：可在界面阅读摘要与阶段日志，或把完整 ZIP 交给 AI。未知指标显示未测，不当作零占用或无故障。
- **自动记录故障与性能瓶颈**：默认开启，仅保存在本机。错误、意外退出和超时会记录；性能需连续两次（至少 3 秒音频）RTF > 1.25，或连续两次明显欠载。内存保护是可预期的资源限制，记录后不自动作为 Bug 提交。
- **自动提交脱敏 Issue**：独立开关，默认关闭。用户开启后授权向本仓库公开提交必要诊断摘要与阶段日志。需要当前机器已有 GitHub 登录凭据（Git Credential Manager、GH_TOKEN 或 GITHUB_TOKEN）；扩展不保存密钥，不使用作者的凭据，也不注册账号。未登录或失败时保留 `*-for-author.zip` 和真实原因，用户可导出或稍后重试。

同类问题 24 小时仅自动记录一份，每天最多三份；同一 Issue 指纹不会反复自动发帖，未登录/失败不循环请求。只保留最近 20 份报告，个人音色、设置与模型不在清理范围。手动采集不受自动记录频率限制。

报告保存在当前 Bot 的 `data/soft-voice/diagnostics`，包含 `REPORT.md`、`diagnostics.json`、`perf.log`、`AI_PROMPT.txt`、`issue-draft.md` 与提交状态。公开 Issue 只附脱敏摘要和必要日志；完整 ZIP 保留本机，界面显示实际 Issue 链接或未提交原因。自动检测只能发现现象，不能替代 AI/作者核实根因。

## 普通用户（命令行备用）

1. 在完整语音安装包中双击 `collect-diagnostics.cmd`。它会寻找 Coopanion，读取语音环境路径；找不到时选择包含 `python/python.exe` 的语音安装目录。
2. 等待完成，在 `diagnostics` 目录找到 `voice-diagnostics-时间.zip`。
3. 将 ZIP 和“怎样触发、预期是什么、实际是什么”交给正在帮你排错的 AI。可以附上当时是否运行游戏、是否首次启动，避免把冷启动和日常回复混为一谈。

旧版 **0.4.11** 也可以使用单独的 `coopanion-voice-diagnostics.zip`：解压、双击即可，不需要先更新扩展。诊断工具使用现有语音包自带的 Python。没有安装语音模型时，先按 [免市场安装教程](INSTALL_WITHOUT_MARKET.md) 部署，不需要为采集日志重新下载模型。

要观察说话期间的性能，在诊断包目录打开 PowerShell，运行下列命令，然后在桌宠中正常发起一段语音：

```powershell
& .\collect-diagnostics.cmd -Seconds 60 -Interval 2
```

最多监测 300 秒。此工具不会发送聊天、关闭程序、替换驱动或压测 GPU。它只观察现有语音进程；诊断进程的输出会显示采样进度。

## 包内有什么

| 文件 | 用途 |
| --- | --- |
| `REPORT.md` | 指标摘要、分析要求与提交方法 |
| `diagnostics.json` | 版本、Windows/CPU、GPU/驱动、Vulkan 内存类型、可用 RAM、语音进程 RAM/CPU、按 PID 区分的独立/共享 GPU 内存、近期播放指标 |
| `perf.log` | 从语音日志中重建的性能阶段与数字，不复制原始日志正文 |
| `AI_PROMPT.txt` | 供 AI 分析的入口文本；公开报障仍需当前用户授权 |
| `manifest.json` | 文件 SHA256，便于核对报告是否完整 |

新版本 worker 会写入不含聊天文本的状态侧文件，记录启动阶段、真实设备和显存分配策略。旧版本没有这些字段时保留空值，不能编造。近期播放数据可能来自上一次会话，分析时要核对时间和存活的 worker；`nvidia-smi` 是整张 GPU 的统计，不能全归为语音占用。

Windows 虚拟环境有时包含一个很小的 Python 启动代理进程。报告中的匹配进程数不等于加载了几套模型，需结合父子进程和内存读数判断。

不采集账号、环境变量、完整配置、聊天、截图、模型、音色参考或生成的音频。路径和常见令牌会遮盖；AI 自己写的分析稿仍需避免引用用户聊天和身份信息。

## 让 AI 分析并提交

复制以下文本给 AI，并附上 ZIP；这段话由**当前用户发送**后才是公开提交的授权：

> 请阅读 https://github.com/scarlet20252025-cloud/coopanion-soft-voice 的 AGENTS.md 和 docs/AI_BUG_REPORTS.md，分析随附诊断包。我授权向该仓库提交脱敏 Issue；先查重，附相关性能日志和诊断数据。区分实测、我的反馈与推测。不能自主提交时，将诊断、分析和 Issue 草稿打成 ZIP 给我，我交回作者 Asryto。不要上传聊天、密钥、完整配置、原始路径或音频。

AI 可使用自己的 GitHub 工具。仓库也提供 `scripts/report_issue.py`，默认只生成草稿与交回作者的 ZIP；加 `--submit` 才请求上传。它使用现有 GitHub 凭据，不索要密码或注册账号。

```powershell
# 在完整语音安装目录运行；文件名换为实际报告。
& .\python\python.exe .\scripts\report_issue.py --diagnostics .\diagnostics\voice-diagnostics-时间.zip --analysis .\analysis.md

# 当前用户已授权公开报障时才使用；已有同类 Issue 可以指定编号补充。
& .\python\python.exe .\scripts\report_issue.py --diagnostics .\diagnostics\voice-diagnostics-时间.zip --analysis .\analysis.md --submit
# --issue-number 1
```

单独诊断包没有另带 Python，可让 AI 使用已安装语音包的 `python/python.exe` 来运行其中的 `scripts/report_issue.py`。脚本会检查报告完整性、检索同一指纹的 Issue；语义相同但不同指纹的问题仍由 AI 查重。GitHub REST 无法直接把 ZIP 附加到 Issue，因此上传的是脱敏诊断摘要和必要性能日志，完整包保留交回用户/作者。

没有登录、网络失败或当前会话不允许公开提交时，生成 `*-for-author.zip`，包含原诊断、`analysis.md`、`issue-draft.md` 和真实 `submission.json`，交给用户。不能用“已上传”描述草稿，也不能丢掉分析与日志。

## 性能判断

- RTF = 合成耗时 / 生成音频时长。小于 1 才表示平均生成快于播放；连续性还需检查实际 `underrunMs` 和 `deviceUnderflows`。
- 首次出声、模型加载、整句合成是三个指标。先缓冲整句可以消除断流，但不能宣称降低首次出声延迟。
- 独显和核显需要分别验收，记录冷/暖启动、驱动、显存分配和背景负载。自动选择仍优先核显，不能在用户未选择时切独显。
- `ok=true` 只表示检查流程执行完成。性能、连续性、听感和其他硬件兼容性需要各自证据。

开发者可用 `python scripts/build_diagnostics.py --output dist/coopanion-voice-diagnostics.zip` 构建独立诊断包。主程序、代码更新包和诊断包使用同一份采集实现。
