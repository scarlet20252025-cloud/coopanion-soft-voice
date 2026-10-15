# AI 完整部署 · Asryto


完整包约 **1.09 GiB**（0.5.2 实测）：主模型解压后约 **924 MiB**，音频解码模型约 **192 MiB**，另含运行库、播放器和扩展。**0.6B 是参数规模，不是几十 MB 的模型**；精简运行组件、推理缓存与模型权重是不同的体积指标。已有兼容模型可只下载代码更新，无需重复下载模型。
默认方案是 GitHub Release 的完整 Windows 便携 ZIP，包含小模型、DLL、Python、音色与 World。无需编译、pip 或云端账号。

## 默认执行

在仓库根目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy.ps1`。脚本读取 `portable-release.json` 的版本、公开 URL、大小、SHA256，校验后解压并调用包内安装器。

如果使用直接下载的 ZIP：解压到英文目录，运行 `install.cmd`。不要把文件拷入作者机器的路径。

安装器先寻找运行进程、快捷方式、安装记录与常见目录。一个有效桌宠自动选定；找不到或多个副本才显示目录选择。可直接传 `-CoopanionRoot`，Bot 默认 companion，其他 Bot 用 `-BotId`。

## 验收与边界

安装先生成本机 `native-runtime.json`，核对模型和音色、枚举 Vulkan GPU（默认核显，独显必须用户明确选择），再真实合成与静音播放，报告 `verification/deployment-check.json`。检查 `ok`、device、音频时长、RTF、`playbackHealth`、断流和错误；该报告不代表真人听感确认。

只有运行时测试成功才接入 World。个人配置保留并备份，安装器兼容 pnpm 扩展链接。支持的桌宠正常退出后安装并重新启动；失败不强制杀进程。路径搬迁后重新运行安装器。

参数：`-RuntimeOnly` 只测试包；`-NoLaunch` 安装后不启动；`-NoEnableSpeech` 保留关闭选择；`-DeviceName` 明确指定核显或独显。主页部署状态区分已安装未连接、就绪、休眠、内存不足与错误。

要求 Windows x64、Vulkan 显卡驱动、至少 3 GiB 可用 RAM；不自行关闭游戏、不自动回退独显、不修改账号。聊天模型是用户自己的配置，语音引擎可以单独验证。

## 备用源码路线

开发者需要重建时，使用 `scripts/deploy-source.ps1`，详细见 [DEPLOY_NATIVE.md](DEPLOY_NATIVE.md)。它从固定公开来源下载模型与工具链、应用仓库补丁、构建精简运行时。Python wheel 本身不是完整模型包。不要将旧 CUDA 安装入口作为默认核显部署。
