> 普通安装推荐 [免编译完整包](PORTABLE_INSTALL.md)。本页保留开发者源码与接口说明。

# 独立轻量化本地语音引擎扩展

World ID：`soft-voice`。npm 包：`cortico-world-soft-voice`。界面名称：**轻量化本地语音引擎**。
已在 Coopanion 0.1.24 接入；不再加载 `cortico-world-cosyvoice-tts`。

## 安装

完成 `scripts/setup-native.ps1` 后，退出桌宠。在仓库根目录运行：

```powershell
$extensions = Read-Host 'Coopanion 扩展目录（含 package.json）'
$bot = Read-Host '当前 Bot 目录（含 config.json）'
.runtime-native\venv\Scripts\python.exe scripts/install_world.py --extensions "$extensions" --bot "$bot" --runtime .runtime-native --enable
```

脚本检查核显运行环境及输出设备，创建独立扩展与本机配置。会取消旧 CosyVoice 扩展注册，保留旧文件。
省略 `--enable` 时安装后保持语音关闭。重启桌宠后在 World 中打开 **轻量化本地语音引擎**。
Python 必须独立安装；安装器会拒绝使用位于旧插件目录中的 Python 本体。

## 功能与边界

控制台分为四页：**语音控制**（开关、试听、音量），**运行状态**（真实延迟曲线、连续播放指标、内存门槛），**配置**（队列与恢复策略），**音色库**（ZIP 导入、选择、教程链接）。
制作音色请阅读 [音色包教程](VOICE_PACKS.md)。新版默认音色预留项标为“待更新”，不可选择。

- 开启、试听、恢复、静音、立即停止并释放模型。
- 音量 0–100；静音直接跳过新句合成，当前已播放句可用立即停止打断。
- 队列上限 1–12 句；满载丢弃最旧。默认 3 句。
- 待说有效期 5–180 秒；默认 45 秒，开始合成前检查，过期不补读。
- 可关闭内存恢复重试；默认每隔至少一分钟检查，空闲达到 4.5 GiB 后尝试加载。
- 展示当前引擎、固定声线、采样率、首次设备回调、排队延迟和断流指标。
- 默认参考音频与种子保持不变，语速 1.0。导入音色须主动选择后重新加载，不自动替换当前声音。
- 模型崩溃或播放错误停止接收并等待恢复，不自动重复可能已播放的半句。
- 新会话跟随当前运行记录，启动/恢复跳过历史消息，避免重新朗读。

桌宠通过 `pet_say` 输出的文本会自动朗读；该扩展负责发声，不负责主动聊天或游戏识屏。
运行数据保存在当前 Bot 的 `data/soft-voice`，包目录只放代码；日志轮转到一个 2 MiB 左右的历史文件。
Python 进程协议仍兼容已有引擎标记，该标记不代表依赖旧 World 插件。

## 验证与打包

```powershell
cd world
npm test
npm pack
```

npm 包包含独立 JS 扩展及控制页，Python、模型和原生引擎由仓库安装脚本提供。
源码包也包含 `world`。无需作者的本地文件、账号或绝对路径；安装器按部署机器生成路径。

## 回退

退出桌宠，使用安装器打印的 `data/soft-voice/backups/<时间>`：将 `bot-config.json` 还原为当前 Bot 的 `config.json`，将 `extensions-package.json` 还原为扩展目录的 `package.json`，然后重启。
这会恢复安装前注册和 World 配置；安装器不会删除旧插件或模型。不要用别人的备份覆盖个人配置。
