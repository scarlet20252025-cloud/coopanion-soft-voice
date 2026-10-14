# 本地语音助手 · Coopanion Local Voice Assistant

为 Windows Coopanion 提供核显流式语音。**0.4.5 / World 0.3.0** 提供独立的本地语音助手：四个独立面板、真实延迟图表、内存要求提示和 ZIP 音色包导入。默认保留已确认的 `soft-child-design-2`，新版默认音色标为“待更新”。工具链、原生引擎源码、模型下载地址与校验值均已公开，无需作者电脑上的任何文件。

0.4.1 使用参考音色特征缓存，实测合成后提交内存减少约 288 MiB，三次对照输出逐字节一致。见[内存优化与复现记录](docs/MEMORY_OPTIMIZATION.md)。0.4.2 另提供可选的[固定音色精简模型构建器](docs/SPEECH_ONLY.md)，无损删除 221 个参考分析张量，模型文件再减少 108.6 MiB；内存基本不变。World 0.2.1 增加可选空闲卸载：配置中设置秒数，默认 0 保持常驻，建议 300；下一句自动唤醒但会增加首句等待。

- [独立扩展安装与控制](docs/STANDALONE_WORLD.md)
- [音色制作、ZIP 打包和导入教程](docs/VOICE_PACKS.md)
- [Cortico 官方接口依据与兼容边界](docs/CORTICO_COMPATIBILITY.md)

Q8 核显版音色已于 **2026-10-12** 通过用户试听并接入正式桌宠。使用 Qwen3-TTS 0.6B Base、固定参考音频和种子，不做变调；明确选择集成显卡，失败时不会改用 NVIDIA 独显或其他声音。不需要云端语音账号、付费服务、PyTorch 或 CUDA。

## 从零部署

先安装 **Windows 10/11 x64、Python 3.10 x64、Git 和显卡厂商驱动（含 Vulkan）**，准备至少 **8 GB 可用磁盘**。核显实测平台为 Ryzen 7 7735H / AMD Radeon(TM) Graphics / 16 GB RAM；其他核显的性能和兼容性需自行验证。启动前要求至少 4 GiB 空闲内存，游戏仍与核显共享系统资源。

```powershell
git clone https://github.com/scarlet20252025-cloud/coopanion-soft-voice.git
cd coopanion-soft-voice
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-native.ps1
```

脚本创建独立 `.runtime-native/venv`，下载带 SHA256 校验的工具链和 Q8 模型，检出固定源码与子模块、应用仓库补丁、编译 DLL、生成本机配置并检查。需要访问 GitHub、PyPI、Google Storage、Hugging Face；下载失败会停止，不会换模型。它不会修改桌宠、注册开机自启或自动播放声音。

**完整操作、设备名选择、试听、插件接入、回滚与故障排查：[核显部署指南](docs/DEPLOY_NATIVE.md)。**

```powershell
# 生成试听文件，不自动播放
.runtime-native\venv\Scripts\python.exe scripts/preview_native.py --output preview.wav
```

参考音频已包含在 [仓库资源](src/coopanion_soft_voice/assets/soft-child-design-2.wav) 和 wheel 中。它是合成音频，不是演员录音；其他人不需要从视频提取音源。不同驱动和硬件不保证逐采样一致，请先试听。

## 接入桌宠

当前推荐独立的 **本地语音助手 World**（Coopanion 0.1.24 已验证），不需要旧 CosyVoice 扩展。完整安装、控制选项和回退见 [独立扩展指南](docs/STANDALONE_WORLD.md)。模型仍使用已确认的 Q8 核显声线。

## 实测与限制

CS2 Dust II 离线机器人练习中，暖机后首次音频设备回调约 **1.18–1.43 秒**，两句无断流或设备欠载，游戏未崩溃。冷启动及预热约 13.8 秒。计时不包含聊天模型回复、排队及扬声器延迟；这不是整场竞技稳定性或 FPS 保证。

固定声线不保证任意句子的语气、音高完全一致。核显仍消耗内存、带宽和功耗；加载时内存不足会拒绝启动。长文本分段生成，帧数耗尽或空音频会报错，不把截断输出标为成功。

- [核显、插件和 CS2 验证记录](docs/NATIVE_TRIAL.md)
- [原 CUDA 后端安装](docs/CUDA.md)：使用独显，不适合游戏隔离目标。
- [CPU 试验及缓存模式](docs/CPU_TRIAL.md)：CPU 实时方案未采用；`cache` 只读打包的固定短语，不支持自由对话。

## 构建与分享

```powershell
.runtime-native\venv\Scripts\python.exe -m pip install build==1.2.2.post1
.runtime-native\venv\Scripts\python.exe -m build
```

分享本仓库或源码包即可按指南重建。wheel 包含 Python 代码、参考声音、缓存和许可证；源码包额外包含安装脚本、固定下载清单、原生补丁及文档。**单个 wheel 不包含第三方 DLL 和 1.28 GB 权重**，不是完整离线安装包。

GitHub Actions 执行 Windows 测试、构建 wheel/源码包；原生安装脚本变化时，还会从干净 runner 下载工具并构建 DLL，也支持手动运行。无 GPU 的 CI 验证构建，不能代替核显推理和真人试听。

这是语音组件，不是整个桌宠或聊天模型服务。角色素材、桌宠程序、聊天模型账号需自行配置。无密钥、聊天记录或作者本机路径依赖。代码 MIT；模型和第三方工具各遵循其许可证，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。
