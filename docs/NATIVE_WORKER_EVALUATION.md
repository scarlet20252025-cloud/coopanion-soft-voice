# C++ 原生工作进程与社区方案评估

作者 Asryto，2026-10-15。结论：优先把已验证的线程池精简、重复 PCM 缓存用于当前流式后端；原生工作进程保留为开发者实验，不自动替换。

## 核查到的实际实现

检索用户提供的描述后，找到了 [Lunar-Astral-Agents 总仓库](https://gitee.com/TayunStarry/Lunar-Astral-Agents)、其现有 `subsystem/core_personality/engine/qwen_tts` 源码，以及历史独立子系统文档。未可靠定位到与引用介绍完全对应的另一份独立仓库，不能把总仓库冒充那个发布包。

| 来源 | 可参考的部分 | 对当前方案的判断 |
| --- | --- | --- |
| [Lunar TTS 子系统](https://gitee.com/TayunStarry/Lunar-Astral-Agents/tree/main/subsystem/core_personality/engine/qwen_tts) | 原生服务、已完成音频的 LRU 缓存、并发请求合并 | 我们已有串行生成队列和直接 stdio 通道，无需添加 Go/HTTP 一跳；采用有字节上限、仅进程内的 PCM 缓存思路 |
| [predict-woo/qwen3-tts.cpp](https://github.com/predict-woo/qwen3-tts.cpp) | C++ 完整管线、独立可执行程序和阶段计时 | 其公开参考接口以 speaker embedding 为主，不能当成现有完整 ICL 音色的直接替换。不能套用另一设备/模型的宣传速度 |
| [当前 qwentts.cpp ABI](https://github.com/ServeurpersoCom/qwentts.cpp/tree/51512f129a7419567f4b8abfb06801451789b8f1) | 原生 tokenization、推理、完整 ICL、PCM 回调 | 保留现有固定音色、Q8 模型及渐进 FP32 KV，独立验证移除 Python 调度层的收益 |

当前模型计算本来就在 C++/GGML 中完成。移除解释器主要影响调度、库和进程开销，不会让神经网络计算自动倍速。Lunar 项目本身使用非商业许可证；本仓库没有复制其源码，缓存与原生进程为独立实现，现有 MIT 许可不变。实验程序依赖的公开 ABI、JSON 库许可见 `native/THIRD_PARTY_NOTICES.md`。

## 本机对照结果

设备 RTX 4050 Laptop / Ryzen 7735H，Qwen3-TTS 0.6B Base Q8，固定完整 ICL、seed 44。不是跨硬件保证。原始数字见 `evidence/2026-10-15-native-worker/`，没有上传参考音频或聊天记录。

- 首个 C++ 实验未同步 Windows C 运行库的环境变量，遗漏文字权重按需加载和渐进缓存设置。首句约 40.5 秒，拒绝接入；修复 `_putenv_s` 与进程环境同步后才继续。现在还校验实际 KV 容量，不能仅凭配置声称优化生效。
- 修复后 C++ 三段 PCM 与各自 Python A/B 对照逐字节一致，含一条跨两段重置参考的长句。一次短句约 1.18 秒，对照约 1.30 秒；长句基本持平。另一轮负载变化后耗时不同，不承诺固定提升比例。
- 首轮原生/旧 Python 的提交量相差约 0.5 GiB，但进一步定位到大部分来自 NumPy/OpenBLAS 的空闲线程池。将原生推理工作进程的 `OPENBLAS_NUM_THREADS` 设为 1 后，Python 就绪提交量约 1829→1349 MiB，休眠约 958→474 MiB；物理驻留分别仍约 1047 / 208 MiB。**不能把提交量下降当成实际 RAM 或显存下降。** GGML 仍使用自己的四线程。
- 去掉无用 BLAS 线程后，C++ 相对 Python 仅剩约 25–40 MiB 的提交/物理驻留差异，仍值得探索更短链路，但不值得牺牲现有流式首声和设备兼容性。
- 新增 4 MiB PCM 缓存的命中处理约 0.38 ms；完整播放器静音设备测试首次回调约 98 ms，零欠载。同句缓存、关闭缓存重新生成，PCM 哈希一致。缓存不加速新句，模型关闭时清空。

系统可用 RAM 启动保护线暂不因线程池优化下调：没有证明加载/推理峰值物理 RAM 相应降低。缓存统计会区分原始生成与复用，纯推理均值排除包含缓存的记录。

## 原生进程开发者构建

实验程序约 1.8 MB，不需要 Python 解释器参与合成；它动态加载完整包中的同一 C++ DLL。**目前仅支持已验证的固定音色精简运行配置和整句缓冲验证，不是正式流式后端，也没有安装进桌宠。** 诊断/安装辅助工具仍使用完整包自带的 Python，不能宣称整个项目零 Python。

准备锁定版本的 qwentts.cpp 公共头文件和 LLVM-MinGW 编译器后：

```powershell
./scripts/build_native_worker_trial.ps1 -QwenSource '<qwentts.cpp 目录>' -Compiler '<LLVM-MinGW 的 x86_64-w64-mingw32-clang++.exe>'
python scripts/check_native_worker_trial.py --exe .runtime/native-worker-trial-build/voice-worker.exe
```

构建脚本固定并校验 JSON 单头库的版本/SHA256，不加载模型或改桌宠。第二条只验证协议与 307 个 Unicode 分段案例，不代表 GPU 或播放验收。

原生实验输入是逐行 JSON，输出沿用 `@@COSY@@` 标记；支持 `sleep`、`wake`、`quit`。实际合成需 `--runtime`、明确的 `--device-name`、与已确认音色完全一致的 `--reference-text` UTF-8 文件；可用 `--no-play --capture <目录>` 比较原始 `.f32` PCM。没有 GPU 时不回退其它设备，不启动第二套模型绕过内存保护。不要让 AI 直接把此实验 EXE 注册为生产 worker。

## 大升级的后续验收顺序

1. 原生流式播放器：保持现有首声、连续性与语句结束回执，气泡必须等设备播放完毕；当前整句验证版不计完成。
2. 取消/恢复、低内存休眠、工作进程残留、错误恢复和诊断报告适配；验证不并驻两个模型。
3. NVIDIA/AMD 核显的冷/热启动、多段长句和缓存失效；Intel UHD 与其他型号仍待实机日志。
4. 按实际物理 RAM、专用/共享显存、RTF、首次设备回调和能效判定采用；失败保留兼容流式后端。不以“纯 C++”替代指标，不降低已验证保护线。
