# 固定音色的精简模型

这个配置只保留文字转语音所需的权重和已提取的内置音色特征。它是无损权重裁剪，不是重新训练或蒸馏。Qwen3-TTS 原本就是专用语音模型，没有一个可删掉的聊天模块。

移除 Talker 文件中的 76 个 `spk_enc.*` 张量与 Codec 文件中的 145 个 `tok_enc.*` 张量，保留文字理解、发音生成、声学码预测、音频解码和完整 tokenizer。保留张量的元数据、精度和原始字节逐项校验；不通过删除汉字、英文、数字或标点词表来假装变小。

| 文件 | 原始字节 | 精简字节 |
|---|---:|---:|
| Talker | 992615488 | 968588160 |
| Codec | 291150624 | 201291104 |

合计减少 113886848 字节，约 108.6 MiB（8.87%）。此前参考缓存已经避免加载这些分析模块，故本轮合成后提交内存 2467.7 MiB 与此前 2468.1 MiB 基本相同；不宣称又省了 109 MiB RAM。三次短/长/短句 PCM SHA256 与完整模型一致，首段回调约 0.80–0.92 秒。实测原始数据见 `evidence/2026-10-14-speech-only/`。

## 构建

先按 DEPLOY_NATIVE.md 安装完整环境，再在仓库根目录运行：

```powershell
$env:PYTHONPATH = "$PWD/src"
.runtime-native/venv/Scripts/python.exe scripts/build_speech_only.py --runtime .runtime-native --output .runtime-speech-only
.runtime-native/venv/Scripts/python.exe scripts/benchmark_reference_memory.py --runtime .runtime-speech-only --variant cached --output speech-only-benchmark.json
```

构建器检查源模型 SHA256，输出新的 GGUF、音色特征、校验清单与配置。输出目录必须不存在，避免覆盖已有环境。没有参考缓存时首次构建会加载完整模型提取，需满足 4 GiB 空闲内存要求。

按独立 World 安装说明接入时，将 `--runtime` 指向 `.runtime-speech-only`。Python 环境与 DLL 沿用本机安装环境；生成的配置包含本机解析出的路径，不是作者电脑上的固定路径。移动目录须重新生成或修正配置并重新验证。普通安装仍默认完整环境。

## 限制与回滚

- 当前精简配置绑定已确认的内置音色。不能现场分析新的参考 WAV；ZIP 文件仍可保存，但切换至其他音色会明确拒绝，不停止现有语音。
- 要更换音色，先将 World 的 runtime-profile.json 中 runtime 恢复为原完整 Runtime，再重启 World。已确认的音色和 UI 设置不需要删除。
- 缺少/损坏特征文件会明确报错，不尝试用已删除的编码器、不默默换音色。
- 构建器保留原模型作回滚，因此本机总磁盘占用暂时增加；上述数字比较的是两套模型各自的体积。
- 继续删除 Talker 层或压缩声学预测器需要训练/蒸馏和重新验收，无法保证当前声音。这个版本是已验证的裁剪范围，不声称是理论最小模型。
