# 本地语音助手 World

独立的 Coopanion API 5 World 扩展。无需安装 CosyVoice 或其他语音扩展。
依赖本仓库提供的 Qwen3-TTS 核显 Python 运行环境，保留固定 soft-child-design-2 音色。

先按仓库核显部署指南运行 `scripts/setup-native.ps1`，然后退出 Coopanion：

```powershell
.runtime-native\venv\Scripts\python.exe scripts/install_world.py --extensions "你的扩展目录" --bot "你的 Bot 目录" --runtime .runtime-native --enable
```

安装器创建当前机器的路径配置，备份旧配置，注销旧 CosyVoice 插件但不删除旧文件。
重启后打开 **本地语音助手 → 语音控制**。无需修改源码中的机器路径。

支持启停、试听、静音、音量、队列上限、过期丢弃、清队列、内存恢复重试与流式播放指标。
语速锁定 1.0；底层已确认的播放链路不支持变速，故不展示无效滑块。
静音跳过新语句；立即停止会中断当前句并释放模型。发生合成错误不自动重复半句。
内存不足会退回文字，空闲达到 4.5 GiB 后可自动重试；模型加载仍要求至少 4 GiB。

源码安装后可在 `world` 目录运行 `npm test`、`npm pack` 打包独立 npm 扩展。
模型、工具链和 Python 依赖通过仓库安装脚本获取，npm 包不内置大型模型。
旧插件的消息解析/日志监听代码按 MIT 派生；许可证保留。运行时无旧插件导入或调用。
