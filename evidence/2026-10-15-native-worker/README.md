# 原生工作进程、线程池与重复 PCM 缓存实测

Asryto，2026-10-15。RTX 4050 Laptop + Ryzen 7735H，现有 Q8 精简模型、完整 ICL、FP32 KV、seed 44。原声参数不变；未录制/上传用户聊天、参考音频或凭据。

- `rejected-environment.json`：首版 C++ 原型的 Windows/C 运行库环境变量不同步，首句约 40 秒，拒绝采用。
- `cpp-python-ab.json`：修正环境变量后的 Python A / C++ / Python B，三段 PCM 完全一致。仅合成对照，不算流式设备验收。
- `blas-one-ab.json`：限制 NumPy/OpenBLAS 单线程后再对照。大部分提交量差异来自空闲 BLAS 线程栈，物理驻留基本没有同等下降。不能将其当成显存下降。
- `pcm-cache.json`：首次生成、命中、关闭缓存重新生成的原始 PCM 哈希一致；最多 4 MiB；静音设备回放首次回调约 98 ms、无欠载，模型关闭清空缓存。
- `actual-worker.json`：直接运行新 CLI worker，未由测试环境预设 BLAS 线程数。就绪提交约 1352 MiB，重复句设备首回调约 63 ms；休眠缓存为零，唤醒仍为空。此报告采自隔离运行配置，不是伪造到用户的运行历史。

102 项 Python / 53 项 World 测试、实际浏览器设备恢复/设置反馈回归通过。实验 C++ 可执行程序独立构建，307 个 Unicode 分段案例与 Python 一致；无 GPU 的协议测试不计推理验证。C++ 原型仍是整句缓冲验证，不默认接入桌宠。

结论与待完成的流式/取消/气泡/多设备验收见 `docs/NATIVE_WORKER_EVALUATION.md`。不以单次最快值承诺所有设备，不据提交量下降调整物理 RAM 启动线。
