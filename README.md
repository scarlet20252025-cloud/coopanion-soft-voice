# 软萌桌宠语音 · Coopanion Soft Voice

把已实际运行的 **soft-child-design-2** 声线与低延迟语音链路保存为可构建、可部署的独立项目。适用于 Windows 上的 Coopanion 桌宠，也可以独立朗读。

当前版本为 **0.2.0 实验版**。保留用户确认的参考音频。GPU 模式使用 **Qwen3-TTS 0.6B Base / BF16 / SDPA / CUDA Graph**，每生成 8 个 codec 帧就开始连续播放。新增不加载模型的原声缓存模式。两种模式均不做变调。

## 游戏模式：固定提示，不占推理显卡

`cache` 模式只播放三条打包的原声录音，整句精确匹配；其他文本保持文字回复，不调用模型、不联网、不用其他声线顶替。它不是自由对话 TTS，也不会把任意回复换成固定台词。

- 我们先学二十分钟，再一起休息一下吧。
- 今天也辛苦啦，先休息一小会儿，我会乖乖等你。
- 你在吗？我来陪你啦，我们慢慢来，好不好？

休息提示使用原始 `soft-child-design-2.wav`；其他两条来自此前通过内容检查的原声克隆输出，缓存模式没有重新合成它们。只播放文件，不保证每条克隆与参考听感完全相同。

已有项目环境时，关闭 Coopanion 后执行：

```powershell
.venv\Scripts\python.exe scripts/install_plugin.py --plugin "D:\Coopanion\data\extensions\node_modules\cortico-world-cosyvoice-tts" --mode cache --keep-disabled
```

安装器保存备份并打印路径。`--keep-disabled` 保持语音关闭；重新打开桌宠后可在 TTS 设置中启用。去掉该参数则安装时开启语音。切换回 GPU 模式用同一命令的 `--mode gpu --runtime .runtime`，会先检查 GPU 和模型；玩游戏时不建议开启 GPU 模式。回滚使用 `--restore` 和打印的备份路径。

缓存模式本身只需 Windows、Python 3.10 和本包，不需要 PyTorch、模型文件或 CUDA。可用 `python -m pip install --no-deps dist/coopanion_soft_voice-0.2.0-py3-none-any.whl` 单独安装，然后用 `python -m coopanion_soft_voice.cli doctor --mode cache` 检查。下方完整环境安装流程是给 GPU 模式的。

实测 Coopanion 插件 IPC 到 Windows 零音量播放正常，缓存 worker 初始化约 392 ms、请求到播放状态约 3 ms。这些是软件时间点，不是扬声器首声测量；尚未进行游戏同时运行的长时稳定性测试。CPU 实时方案未通过：当前 INT8 内容错误，FP32 内容正确但短句合成约 22.7 秒，均未部署。详情见 [CPU 与缓存测试](docs/CPU_TRIAL.md)。

> 这是语音组件项目，不是完整 Coopanion 分发包。桌宠程序、角色素材与聊天模型账号由用户自行配置。本仓库不包含 API 密钥、聊天记录、他人视频音源或多 GB 模型权重。

## 已验证的效果与边界

- 原环境：Windows、RTX 4050 Laptop 6GB、Python 3.10、Coopanion 0.1.21、社区 TTS 插件 0.1.11。
- 原链路实测：收到朗读文本后约 **0.69～0.86 秒**进入播放，音频设备回调约 **0.72～0.88 秒**；短句测试没有缓冲断流。详见 [验证记录](docs/VALIDATION.md)。这些不是所有机器的保证，也不包含聊天模型思考或前一句排队。
- **偶发声线变化尚未查明原因。** 固定参考音频不代表所有句子的音高、语气都完全相同；自动转写正确也不等于听感一致。流式模式与整句解码存在小幅数值差异。
- 首次启动需要加载模型和预热；等待 `ready` 后才进入上述延迟范围。长文本仍按不超过 60 字分段，多个请求串行排队，GPU 忙碌可能增加延迟。

## 安装与独立使用

需要 Windows 10/11 x64、NVIDIA CUDA 可用显卡、Python **3.10**。测试显存为 6GB；建议至少预留 12GB 磁盘空间用于环境、缓存与模型。显卡驱动必须支持 CUDA 12.1。

```powershell
git clone https://github.com/scarlet20252025-cloud/coopanion-soft-voice.git
cd coopanion-soft-voice
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

脚本会建立独立 `.venv`，安装已固定的主要依赖，下载指定提交的模型并校验权重，再检查 GPU 和音频设备。不会设置开机自启，也不会修改系统音量。模型下载需要访问 Hugging Face。

```powershell
# 检查环境
.venv\Scripts\python.exe -m coopanion_soft_voice.cli --runtime .runtime doctor
# 首次调用会预热；持续使用请通过 Coopanion 的常驻 worker
.venv\Scripts\python.exe -m coopanion_soft_voice.cli --runtime .runtime speak "我们先学二十分钟，再一起休息一下吧。"
# 生成文件，不自动播放；测试句子限制 60 字以内
.venv\Scripts\python.exe -m coopanion_soft_voice.cli --runtime .runtime render "今天也辛苦啦。" --output demo.wav
```

如果已下载模型，将完整文件放在 `.runtime/clone-model`，可用 `scripts/setup.ps1 -SkipModelDownload` 跳过下载。不要放入其他 Qwen 模型；模型文件清单和提交号已锁定。

## 接入 Coopanion

1. 从 [Coopanion 官方项目](https://github.com/Pal-AI-Lab/Coopanion) 安装桌宠；已验证版本为 0.1.21。
2. 在 Coopanion 的社区扩展界面安装 **`cortico-world-cosyvoice-tts@0.1.11`**。无需先下载 CosyVoice 模型；本项目安装完成后将使用独立 Qwen 环境。
3. 退出 Coopanion，找到插件目录（其中应有 `package.json`、`src`、`runtime`），执行下列命令。把示例路径替换为自己的真实安装路径。

```powershell
.venv\Scripts\python.exe scripts/install_plugin.py `
  --plugin "D:\Coopanion\data\extensions\node_modules\cortico-world-cosyvoice-tts" `
  --runtime .runtime
```

4. 重启 Coopanion，等待语音状态为 `ready`。这一步需要重新加载 JavaScript，仅在界面关开语音不能替代应用重启。

安装器只支持插件 **0.1.11**，遇到版本或源码结构不匹配会停止。它保存安装前的备份，锁定参考音频、语速 1.0、音量 65%；不会修改聊天模型账户配置。不要移动安装后的项目或虚拟环境，否则需要重新安装接入配置。社区插件升级可能覆盖补丁，升级后需要重新检查兼容性。

```powershell
# 回滚：使用安装器输出的真实备份目录，再重启 Coopanion
.venv\Scripts\python.exe scripts/install_plugin.py --restore "D:\...\.cosyvoice-tts\softvoice-backups\时间戳"
```

## 构建与分享

```powershell
.venv\Scripts\python.exe -m pip install build==1.2.2.post1
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Python .venv\Scripts\python.exe
```

产物是 `dist/` 中的 wheel 和源码包。GitHub Actions 会运行无需 GPU 的测试、构建两种包并提供下载。完整部署建议分享仓库地址或源码包；wheel 只包含推理代码、固定音频、许可证和模型清单，GPU 依赖请按安装脚本安装。由于 CUDA 安装源特殊，本包不让 pip 自动选择 torch 版本。

主要推理依赖与本次验证环境的传递依赖版本分别固定在 `requirements-runtime.txt` 和 `requirements-runtime.lock`，并非逐字节锁定的系统镜像。模型固定到 HF 提交 `5d83992436eae1d760afd27aff78a71d676296fc`。音频 SHA-256 为 `4d47133ec965474fb546110c521541d0a6d610f8b84a02b1a575404c6fa63f20`，启动时校验。

## 来源与许可证

项目代码采用 MIT；CUDA Graph 解码器保留上游 MIT 声明。固定参考 WAV 是 Qwen VoiceDesign 生成并由用户确认的合成音频，不是视频原声或钉宫理惠录音。模型、桌宠程序及外部角色资源遵循各自许可证。详见 [第三方说明](THIRD_PARTY_NOTICES.md)。
