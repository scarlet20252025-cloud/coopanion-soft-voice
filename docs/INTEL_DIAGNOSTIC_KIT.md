# Intel UHD 核显一键测试 · Asryto

适用于已经安装轻核语音完整运行时的 Windows 10/11 x64 电脑。免装 Python、免下载模型、免填命令。**这是诊断工具，不是性能修复版。**

1. 将工具 ZIP 全部解压（不要在压缩包内直接运行）。
2. 双击 **START.cmd**。工具自动识别桌宠关联的语音安装目录和 Intel 核显。多个安装会列出序号，找不到才弹出目录选择。
3. 等窗口显示完成，把 **reports 文件夹中本次生成的 ZIP** 发回作者。失败也会生成故障报告。

测试时会显示已完成组数、当前合成阶段和已用秒数，每两秒刷新，不伪造百分比或剩余时间。共四组，每组上限 15 分钟。只生成固定测试句到本地文件，不播放声音，不读取聊天，不自动提交 Issue。

若提示语音正在运行，请在扩展中点击“停止语音”，按回车继续；测试完成后自行恢复开启。至少保留原有 3 GiB 可用系统内存要求，不修改阈值，不自动关闭任何用户程序。请接通电源，并告诉作者是否同时运行游戏/录屏、电源模式是什么。

工具不修改安装目录、桌宠设置、GPU 选择或音色。缓存和临时运行配置只写在 reports 内。实验可产生不同音频，但不会成为你的默认音色。报告自动排除运行配置、模型和 WAV，并对日志路径、邮件地址及常见密钥格式脱敏；发送前仍可自行打开 ZIP 查看。WAV 只留本地，结束后整个工具目录可删除。

## 给 AI agent / DSH

优先让用户双击 START.cmd。无交互调用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_gpu_diagnostic.ps1 -NoPause
```

无法唯一发现运行时才添加 `-Runtime '实际语音目录'`。默认只接受唯一 Intel 核显，不能自动改成独显；工程师可用 `-Device '实际 Vulkan 核显名称'` 显式测试其他核显。`-PreflightOnly` 只检查发现、枚举和打包，不执行合成，其成功不能算性能通过。

请不要要求用户提供账号、API key、登录令牌，不要下载另一个模型，不要关闭用户程序或修改其默认设备来凑通过。退出码 0 表示本次流程完成，非 0 为未完成；查看 ZIP 中 status.json 的 synthesisAttempted / preflightOnly，以及 comparison.json。firstChunkMs 不是扬声器出声，RTF 降低但 PCM 改变不能直接判为无损提速。acceptedForRelease 永远为 false。

问题关联：[Issue #13](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/issues/13)。用户明确授权且有 GitHub 凭据时，先检查该 Issue，再补充脱敏结果；否则直接交回生成的 ZIP，不自行公开。原生 Intel 优化仍待这台机器的实测，不能关闭问题或宣称已修复。
