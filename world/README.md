# 轻核语音 · Qwen3-TTS 超轻量高速语音引擎

作者：**Asryto** · npm 包 `cortico-world-soft-voice` · Cortico World API 5

Coopanion 的独立本地 TTS 扩展，使用 Qwen3-TTS 0.6B Base Q8、Vulkan 核显/独显和已确认的 `soft-child-design-2` 音色。无需旧 CosyVoice 扩展、语音 API key、PyTorch 或 CUDA。

## 特点与优势

- **离线发声，无语音接口费用**：模型部署后在本机合成，不向云端语音服务发送朗读内容；桌宠的聊天模型账号仍单独配置。
- **轻量模型，较低显存占用**：Q8 模型配合渐进 KV 缓存、计算图精简和按需文本嵌入。本机 RTX 4050 Laptop GPU 正常合成专用显存实测约 1045 MiB（1.02 GiB），并非所有设备的保证，也不是系统 RAM 要求。[实测对照](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/PERFORMANCE_0.5.2.md)
- **核显、独显可选**：使用 Vulkan；支持明确选择推理设备，显示保存、切换和实际生效状态，不偷偷换到其他显卡。
- **流式播放与气泡同步**：边生成边播放，气泡可等待当前段读完再切换；慢设备可用整句缓冲优先保证连续播放。
- **可选低功耗休眠**：空闲时释放模型，下一句自动唤醒；显示唤醒进度，首次出声会多出加载时间。
- **易部署、易排错**：完整包自带模型与运行环境，自动寻找 Coopanion；界面提供延迟、内存、断流指标和可导出的诊断报告。

**不需要用户单独安装 Python，但完整运行包仍内置 Python 播放与控制组件；不是零 Python 项目。**

**npm 市场包只包含 World 与控制界面。使用语音前需要安装 Qwen3-TTS 小模型和本地运行环境。** World 0.4.7 起可在主页点击「一键下载并安装」，默认优先魔搭国内镜像，支持进度、取消、续传和 SHA256 校验；也可导入完整 ZIP。已有有效模型直接保留。文件存在、合成验收通过、连接、休眠和等待内存分别显示。

## 安装

1. 下载 [完整 Windows 便携安装包](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/releases/latest)，解压到英文路径，双击 `install.cmd`。自带小模型、Vulkan 引擎、Python 3.12 和依赖；自动寻找 Coopanion，找不到或多个副本时再选择。
2. 完整包会自动安装 World 并登记语音路径；无需扩展市场、npm 账号，也不需要再安装 TGZ。
3. 打开 **轻核语音 · Qwen3-TTS 超轻量高速语音引擎 → 语音控制**。播放状态在左、模型部署检测在右；窄窗口上下排列。

要求 **Windows 10/11 x64、厂商 Vulkan 显卡驱动**。核显加载前至少 3 GiB 系统可用内存，自动恢复线 3.5 GiB；已验证渐进 FP32 KV 布局的 NVIDIA 独显为 2.75 / 3.25 GiB，旧运行时或未识别设备不套用降低后的门槛。默认自动选择核显，独显需用户明确选择；缺驱动或加载失败会报错，不自动回退其他显卡。AMD 核显及 NVIDIA RTX 4050 Laptop GPU 已实测，Intel 核显尚未作者实机验证。其他硬件的兼容性与性能需实际检查。

完整包不包含桌宠程序、角色或聊天模型账号。保留解压目录，模型与 Python 从其中运行；迁移到别的英文路径后重新执行安装器。本地文件扩展从 GitHub 完整包更新，不查询 npm。详细步骤见 [不依赖扩展市场的安装教程](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/INSTALL_WITHOUT_MARKET.md)。

## 功能

- 同一个按钮控制启用、加载取消和停止；显示真实加载阶段、等待时间和成功/失败状态。
- 流式朗读 `pet_say`，音量、试听、清队列、过期丢弃、有限排队及性能曲线。
- 独立气泡同步选项：首次默认开启，等本段实际读完后再切换下一段；关闭只恢复文字计时，保留手动选择。
- 可选低功耗模式：空闲或内存紧张时释放模型，不打断当前播放；下一句话自动唤醒。可保留工作进程或完全退出。休眠不会被误报为未部署。
- 进程内存、启动保护、首次出声、断流和设备欠载的真实数据；没有实测时不编造数值。
- 音色 ZIP 导入入口和制作教程，未来默认音色标为“待更新”。当前固定音色精简模型锁定已确认声音；自定义音色需要完整运行时。
- 按 Cortico 官方 `envPrompt` 注入实际语音能力和近期回复回执；静音、故障、休眠状态如实说明，避免上下文交接后重复回答。

原速 1.0、种子和采样参数保持固定。出现部分合成失败时不重复补读，不偷偷换默认声音。低功耗减少空闲占用，不代表合成时无需内存。界面进程指标不能当成总显存占用。

## 教程与源码

- [最简安装与排错](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/PORTABLE_INSTALL.md)
- [音色制作与 ZIP 打包](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/VOICE_PACKS.md)
- [官方 Cortico 接口与气泡桥兼容范围](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/CORTICO_COMPATIBILITY.md)
- [内存优化与验证记录](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/MEMORY_OPTIMIZATION.md)
- [报告问题](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/issues)

当前气泡显示桥适配官方桌宠包 0.1.4，完整安装器会安装；未知版本或结构变化会提示。单独市场扩展不会自动下载模型、修改聊天账号或注册开机自启。

代码 MIT。原生引擎、模型和 Python 等依赖保留各自许可证，见仓库第三方说明与完整包的 licenses 目录。

## 播放与更新

0.4.0 增加自动/连续/开口优先策略、空闲时切换核显或用户明确选择的独显，以及主页右上角代码热更新。语音引擎立即生效，World 代码在重启桌宠后加载；详见 [说明](https://github.com/scarlet20252025-cloud/coopanion-soft-voice/blob/main/docs/PLAYBACK_AND_UPDATES.md)。
