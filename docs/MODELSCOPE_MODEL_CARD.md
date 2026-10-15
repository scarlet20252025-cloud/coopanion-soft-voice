---
license: apache-2.0
tasks:
- text-to-speech
---

# 轻核语音 · Qwen3-TTS 超轻量高速语音引擎

作者：**Asryto**。

本仓库是 [coopanion-soft-voice](https://github.com/scarlet20252025-cloud/coopanion-soft-voice) 的国内部署资源镜像。提供与 GitHub Release 字节一致的 Windows x64 完整安装包，供 Coopanion World 扩展及离线安装使用。

## 安装

下载 `coopanion-local-voice-0.5.3-windows-x64.zip`，核对同名 `.sha256` 文件，解压后双击 `install.cmd`。安装器自动寻找 Coopanion；找不到时再手动选择。保留已安装的较新扩展和个人设置。

包内含定制裁剪的 Qwen3-TTS 0.6B Base Q8 推理资源、音频解码模型、原生推理库、播放器、便携 Python 和 World 扩展。无需另外安装 Python、Git 或编译工具。这不是重新训练的新基础模型，也不是几十 MB 的完整 TTS 模型；完整 ZIP 约 1.09 GiB。

此镜像固定提供引擎 0.5.3 / World 0.4.6 的已验证资源。新 World 的一键部署入口仍处于开发验收阶段，不能仅安装此旧包便认为获得尚未发布的新功能。

## 设备和内存

要求 Windows x64 和支持 Vulkan 的厂商显卡驱动。默认自动选择可识别的唯一核显；独显需用户主动选择。核显启动保护线为 3 GiB 可用系统内存，已验证的 NVIDIA 优化布局为 2.75 GiB；其他硬件不保证相同占用或速度。显存、系统内存和下载体积是不同指标。

## 来源及许可证

模型来源：[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)，原生推理来源：[qwen3-tts.cpp](https://github.com/predict-woo/qwen3-tts.cpp)。模型遵循其上游 Apache-2.0 许可；轻核语音代码为 MIT。完整包包含 `LICENSE`、`THIRD_PARTY_NOTICES.md` 和各运行库许可证，其他组件以各自许可证为准。

性能数据和局限见源码仓库 `docs/PERFORMANCE_0.5.2.md`，不将单台设备结果作为所有设备的保证。问题反馈请使用源码仓库 Issues，提交前移除令牌、账号、个人聊天和私密路径。
