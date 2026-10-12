# 原生推理试验（2026-10-12，未部署）

目标是保留 `soft-child-design-2` 参考声线，支持任意聊天，降低等待时间，并避开游戏使用的 NVIDIA 显卡。这里记录隔离测试，不代表生产功能已经完成。

## CPU 结论

采用 [qwentts.cpp](https://github.com/ServeurpersoCom/qwentts.cpp) 的完整 ICL 参考音频与文字接口。原始参考文件 SHA256、seed 44 保持不变；原生引擎与量化会改变采样结果，不能因此保证音色与原版相同。新样本全部待人工确认，没有播放、缓存或替换正式语音。

平台：Ryzen 7 7735H，16 GB RAM，Windows；BelowNormal 优先级。以下是单次测量，不是稳定性或游戏共存测试。

| 配置 | 暖机短句连续播放所需缓冲 | 结论 |
|---|---:|---|
| Q8，CPU 4 线程 | 约 4.3–4.5 秒 | 慢于目标 |
| Q8，CPU 8 线程 | 约 2.8–3.3 秒 | 三句 ASR 内容正确，但仍慢于实时 |
| Q4，CPU 8 线程 | 最后一条短句约 1.84 秒 | 两轮 ASR 疑似漏读“会”，不能按速度直接选用 |
| Q4，CPU 8 线程，长句 | 4.19 秒 | 11.68 秒音频生成耗时 15.39 秒；峰值工作集约 3.1 GB，未达目标 |
| Q8，OpenBLAS 4 线程 | 第二句约 5.57 秒 | 修复算子分配后可运行，但比普通 CPU 慢 |

第一帧回调通常只含很短的音频，不能把约 0.3 秒的首次回调时间宣传成不中断的首声延迟。`continuous_start_seconds` 按各分块到达时间减去此前音频总时长计算，是这条测量轨迹下避免缓冲耗尽所需的最小起播等待，不含声卡、应用和系统调度开销。真实播放需要额外余量。

Q4 长句 ASR 基本完整，但 ASR 不能判断软萌程度、自然度或音色一致性。Q4 短句两次识别为“我乖乖等你”，预期“我会乖乖等你”，保留为待核实问题。

全句批量解码比流式解码慢，已排除。OpenBLAS 不能直接执行声码器的全部算子；试验补丁通过 CPU/BLAS 调度器执行静态图，避免将 `CONT` 等不支持的算子直接交给 BLAS。该补丁只用于复现试验，未接入正式安装程序。

## 复现

固定源码、GGUF 修订和文件散列位于 `evidence/2026-10-12-native/manifest.json`。同目录保留原始分块时间、ASR 文本及试验补丁。模型与第三方工具未提交到仓库。

1. 检出固定 qwentts.cpp 修订及其 ggml 子模块，应用 `qwentts-experiment.patch`。
2. 使用 CMake、Ninja、LLVM MinGW 构建 Windows Release：`GGML_CUDA=OFF`、`GGML_VULKAN=OFF`、`GGML_OPENMP=OFF`、`GGML_NATIVE=ON`、`QWEN_SHARED=ON`，目标 `qwen`。
3. 在项目 Python 3.10 环境运行 `scripts/native_trial.py`，指定 `--dll`、运行库 `--dll-dir`、`--model`、`--codec`、`--output` 和 `--threads 4` 或 `8`。
4. 可用 `--texts-json` 传入 UTF-8 文本列表。最长生成默认 240 帧，生成阶段 60 秒取消；这是回调级取消，不是能中止所有原生库故障的外部 watchdog。
5. 用独立 CPU ASR 复核内容，再人工确认音色。不要将试验输出自动加入生产缓存。

短句测试的首条还包含首次 ICL 声码器状态建立，须与后续暖机结果分开报告。长句曾因 120 帧测试上限提前结束，该次数据不作为长句内容验证；有效长句复测使用 240 帧上限。

## 核显路线

本机 Vulkan 枚举确认 NVIDIA 独显与 AMD 核显均可见。核显试验必须显式限制 `GGML_VK_VISIBLE_DEVICES` 到已核实的 AMD 设备；不能依靠默认 GPU 选择。设备序号可能随驱动变化，不应硬编码到正式部署配置。

Q8 核显实测：两条暖机短句的连续起播缓冲约 0.46–0.53 秒；长句 10.56 秒音频在 7.60 秒内生成，所需缓冲约 0.37 秒。短句 ASR 内容完整，长句只有同音字“再/在”差异。未自动将 ASR 当作音色验收。

使用 1.2 秒音频预缓冲，在真实 Windows 声卡上零幅度播放六轮，首次设备回调：冷启动约 2.66 秒，其余约 1.02–1.05 秒，全部 `underrun=0`、`deviceUnderflows=0`。两条文本分别重复三次，各自 WAV 的 SHA256 完全相同。该结果验证当前配置下的重复性，不能保证任意文本的听感一致。

随后通过正式 `cli worker --mode igpu` 协议测试短句、长句、跨分段长回复：首次设备回调为 1258、1104、1175 ms；最长输出 21.12 秒，三条均无断流，进程正常退出。证据 `native-worker.json`。测试为零幅度输出，不是麦克风测得的扬声器首声延迟，也未包含聊天模型等待。

最后在隔离的真实插件副本上运行 Node → `CosyRuntime` → Python worker → Windows 声卡：初始化与预热 8248 ms，ready 后两条请求首次设备回调 1301、1090 ms；均无断流、设备欠载或插件错误。证据 `native-plugin.json`。副本用当前安装插件源码升级，正式插件未改动。

峰值进程工作集约 3.7 GB；这个数不等于核显共享内存加进程的全部开销。即使避开独显，仍会占用共享内存和整机功耗。**尚未经过用户音色试听，正式模式未切换。**

### CS2 共存测试与 0.3.1 边界修复

在本机 CS2 Dust II 离线休闲练习、机器人正常活动、玩家站立的场景中，进行了 10 秒语音关闭基线及一次核显 worker 启动与两句静音声卡播放。共采集 37 个样本、约 42 秒。游戏进程始终存活，之后界面仍显示正常对局；测试结束退出该离线场景。

- 启动与预热 13.816 秒；ready 后短句和长句首次设备回调分别 1426、1182 ms，均无断流或设备欠载，插件没有错误。
- NVIDIA 全卡显存基线 5104–5109 MiB，语音阶段 5102–5106 MiB；未观察到语音引发独显显存增长。这是系统整体显存观测，不是逐进程精确归因。
- 空闲 RAM 基线约 5300–5382 MiB，语音期间最低 3047 MiB。
- 证据为 `cs2-coexistence.json` 和 `cs2-native-plugin.json`。这不是 FPS/帧时间基准，也不是长时间、移动或竞技对局稳定性保证。

原生 API 达到帧数上限时仍会返回成功。0.3.1 新增帧数耗尽和空音频检查，避免把可能截断的语音标成完成；长回复分段会忽略独立空白片段，避免末尾换行令整个请求报错。新增模拟原生回调的限额、空输出、播放失败和下一条恢复检查，以及尾部换行回归测试；共 21 项测试通过。声线、模型参数、预缓冲长度未改变。

## 可选后端与构建

0.3.0 新增显式 `igpu` 模式，默认仍为原来的 `gpu`，不自动切换已安装插件。核显后端不导入 PyTorch。它检查 Q8 模型和 DLL 散列、固定引擎修订、参考音频、核显名称及设备类型；核显不匹配时停止，不回退 NVIDIA。启动前空闲 RAM 少于 4 GiB 时拒绝加载。这是保护门槛，不是已经测过的游戏稳定性保证。

独立核显环境使用 Python 3.10，执行 `python -m pip install -r requirements-native.txt` 后安装本项目 wheel；无需安装 CUDA 或 PyTorch。完整 GPU 环境的 `setup.ps1` 不是核显模式的必要步骤。

`scripts/build_native_windows.ps1` 接收固定源码、LLVM MinGW、CMake、Ninja、Vulkan Headers/import library、glslc 和已安装 SPIRV-Headers 路径，检查源码提交并应用试验补丁，构建 DLL。测试工具链为 llvm-mingw 20261006、CMake 4.4.4、Ninja 1.13.2；Vulkan Headers 1.4.328、SPIRV-Headers vulkan-sdk-1.4.328.1、Google shaderc 20261001 Windows VS2022 构建。DLL 未随 wheel 分发；跨机器需要构建，不要只复制 Python 包后声称部署完成。

在 runtime 下创建 `native-runtime.json`（这里是字段示意，路径和散列需替换）：

```json
{
  "dll": "C:/native/qwentts/build-vulkan/libqwen.dll",
  "dllSha256": "构建所得 DLL 的 SHA256",
  "model": "C:/native/models/qwen-talker-0.6b-base-Q8_0.gguf",
  "codec": "C:/native/models/qwen-tokenizer-12hz-Q8_0.gguf",
  "dllDirectories": ["C:/native/llvm-mingw/bin"],
  "deviceName": "AMD Radeon(TM) Graphics"
}
```

使用 `python -m coopanion_soft_voice.cli --runtime .runtime doctor --mode igpu` 检查；确认试听后才通过 `scripts/install_plugin.py --mode igpu --runtime .runtime --keep-disabled --plugin ...` 安装并重启桌宠。之后可在界面启用语音。安装器会备份原设置；在此之前可用 `scripts/native_trial.py` 生成候选 WAV，不自动播放。该核显后端需要 NumPy、soundfile、sounddevice，以及本机构建的 DLL 和对应运行库。
