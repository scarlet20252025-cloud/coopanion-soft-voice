# 工程交接与接管说明

作者 **Asryto**。这一页写给接手本仓库的人或 AI（包括转到 DSH 后的开发线）。建议顺序：本页 → [工程进度与当前交付](PROJECT_STATUS.md)（当前版本、验收边界、未完成项）→ [AGENTS.md](../AGENTS.md)（部署与维护硬规则）。本页解释**为什么这样做**，那两页规定**必须怎么做**。

## 1. 交接时点的状态

| 项目 | 状态 |
| --- | --- |
| 引擎 / World | 0.5.8 / 0.4.11，Release `v0.5.8` 与 `updates-v0.5.8` 均已发布 |
| npm 市场 | `cortico-world-soft-voice@0.4.11` 已发布，`dist-tags.latest` = 0.4.11 |
| main 分支 | 已包含 PR #20（气泡同步修复，CI 通过）；本页随该次提交一并入库 |
| 本机扩展 | 市场副本与 `local-soft-voice` 均已升到 0.4.11，**等待重启 Coopanion 生效** |
| 本机引擎 | 运行时目录内实际为 0.5.5 内容，可通过扩展右上角更新提示升到 0.5.8 |
| 本轮实机核对 | 用本机真实桌宠页面（`cortico-world-desktop-pet` 0.2.0）跑气泡桥判定：标记、浏览器端脚本、四个调用点齐全，`bridgeProblem()` 返回 `null` |

发布核对证据：Release 资产大小与 `portable-release.json` 记录的 1169757822 字节一致；匿名下载更新包 `coopanion-voice-update-0.5.8.zip`，字节数与 SHA256 与 `update-release.json` 完全一致；`releases/latest` 指向 `v0.5.8`。

## 2. 项目是什么

一个 **Windows 上的 Coopanion 独立语音扩展**：桌宠通过 `pet_say` 输出的文字会被自动合成并播放，不需要语音 API key，也不依赖云服务。它由两部分组成，版本分别演进：

- **引擎**（Python + 原生 C++ `libqwen.dll`，Vulkan 推理，版本形如 `0.5.x`）：把 Qwen3-TTS 0.6B Base Q8 的精简版跑在核显或独显上，负责合成、分句、播放、休眠、设备切换、热更新与诊断。
- **World 扩展**（JavaScript，版本形如 `0.4.x`，npm 包名 `cortico-world-soft-voice`，World ID `soft-voice`）：Coopanion 加载的界面与控制层，负责开关、状态、配置、音色库、气泡同步、部署与报障。

历史脉络：最早沿用上游 CosyVoice 插件（`cortico-world-cosyvoice-tts`），后来拆成独立项目并换成原生 Qwen3-TTS 推理；`scripts/install_world.py` 会取消旧插件注册、保留旧文件。0.5.0 起原生模型在本机 AMD 核显与 RTX 4050 验证通过；0.4.10 完成 Coopanion 0.2.1 的 world 契约 6 迁移。语音不再依赖任何其它语音插件。

## 3. 版本与交付物

四条渠道各自独立，同版本必须字节一致：

| 渠道 | 位置 | 内容 | 用途 |
| --- | --- | --- | --- |
| 正式完整包 | Release `v0.5.x` | 约 1.09 GiB，含模型、Python 3.12、Vulkan DLL、World tarball、`install.cmd` | 面向新用户的唯一完整安装，`releases/latest` 只放它 |
| 代码更新包 | 预发行 `updates-v0.5.x` | 约 1 MiB，只替换代码与安装脚本 | 扩展右上角「下载并热更新」，不重下模型 |
| npm 市场 | `cortico-world-soft-voice` | 纯 JS 扩展 + 面板 + 文档 + `describe.json` | Coopanion 扩展市场与手动 npm 安装 |
| 国内镜像 | 魔搭 `Asryto/QingHe-Qwen3-TTS` | 完整包副本 | 无代理环境的一键部署 |

版本号三处必须同步：`src/coopanion_soft_voice/__init__.py`、`world/package.json`、`portable-release.json` / `update-release.json`。

## 4. 代码地图

引擎侧（`src/coopanion_soft_voice/`）：

| 文件 | 职责 |
| --- | --- |
| `native_engine.py` | 原生库绑定与推理调用，流式合成入口 |
| `decoder.py` | 原生输出到 PCM 的解码与拼接 |
| `playback.py` / `pcm_player.py` / `start_buffer.py` | 播放策略（自动 / 连续优先 / 开口优先）、欠载统计、起播缓冲 |
| `phrase_cache.py` / `pcm_cache.py` / `reference_cache.py` / `integrity_cache.py` | 重复语句缓存（≤4 MiB）、PCM 与参考特征缓存及校验 |
| `memory_policy.py` / `memory_metrics.py` | 启动保护线与内存读数，设备布局相关的门槛都在这里 |
| `updates.py` | 热更新：清单获取、成员白名单、下载、备份、安装、回滚 |
| `world_package.py` | World 包投影与 `ROOT_FILES` 名单，安装器与构建器共用 |
| `diagnostics.py` / `reports.py` / `issue_reporting.py` | 诊断采集、本地报告、脱敏 Issue |
| `cli.py` | 子命令 `download` / `devices` / `doctor` 系列 / `speak` / `render` |
| `gpu_memory.py`、`native_capabilities.py`、`voice_pack.py`、`speech_text.py` | 设备探测、能力标记、音色包、可朗读文本处理 |

扩展侧（`world/src/`）：

| 文件 | 职责 |
| --- | --- |
| `index.js` / `definition.js` | World 定义、`preflight`、`create`、`describe` |
| `world.js` | 主类：状态机、`envPromptVars()` 提示词注入、配置校验、工具调用、设置持久化 |
| `runtime.js` | worker 生命周期、阶段（`load_model`、`ready`、`sleeping`、`waiting_memory` 等）、内存门槛、设备探测 |
| `deployment.js` | 一键部署：下载源选择、断点续传、校验、解压、设备选择 |
| `updates.js` | 调用 Python 更新器并把进度转成界面状态 |
| `bubble-sync.js` / `bubble-bridge.js` / `bubble-client.js` | 气泡同步的同步器、适配桥与浏览器端客户端 |
| `voices.js` | 音色库与 ZIP 导入、教程链接 |
| `reports.js` 等 | 界面侧的诊断与报障入口 |
| `dist/webui-0.4.11.js`、`dist/console-*.js` | 面板产物。**这些是手写源码，不是构建输出**：新界面版本的做法是复制上一版文件再改，并把 `package.json` 的 `webUiClient` 指过去 |

脚本与测试：

- 构建与发布：`scripts/build_portable.py`、`scripts/build_update.py`、`scripts/build_speech_only.py`、`scripts/publish_release.py`（`prepare` / `publish` / `inspect`）。
- 安装与验证：`scripts/install_world.py`、`scripts/install_bubble_bridge.py`、`scripts/verify_deployment.py`、`scripts/verify_install_channels.py`、`scripts/verify_console_controls.cjs`、`scripts/deploy.ps1`、`scripts/deploy-source.ps1`。
- 性能与诊断：`scripts/benchmark_*.py`、`scripts/collect_diagnostics.py`、`scripts/gpu_memory.py`、`scripts/run_gpu_diagnostic.py`、`scripts/report_issue.py`。
- 测试：`world/test/*.test.js`（Node，含 `contract.test.js`，等价于官方 `pnpm check:extension`）与 `tests/*.py`（`python -m unittest discover -s tests`）。CI 见 `.github/workflows/build.yml`。

## 5. 不能碰的硬规则

1. **内存保护线只能往上调。** `memory_policy.py` 与 `world/src/runtime.js` 里：核显 3.0 / 3.5 GiB；已实测的 NVIDIA 渐进 KV 布局（`adaptiveKv` 且 `vendorId == 0x10de`）2.75 / 3.25 GiB；其它紧凑布局 3.25 / 3.75 GiB；标准布局 4.0 / 4.5 GiB。旧 DLL、旧布局、未识别设备一律用更保守的值。只有实测峰值确实下降，才动对应设备的门槛。
2. **市场元数据（`world/describe.json`、`world/CHANGELOG.md`）永远不进代码更新包。** 更新包由**用户机器上已装的引擎**解压校验，白名单写在那个引擎里。`build_update.py` 会剔除这两个文件，并用冻结的历史白名单 `updates.legacy_permitted` 逐个核对，不合规直接拒绝构建。
3. **白名单有两份，改一处必须改另一处。** `world_package.py` 的 `ROOT_FILES` 与 `updates.py` 的 `permitted` / `legacy_permitted` 是同一份名单的不同用途副本。
4. **不动桌宠本体。** 不允许改 `cortico-world-desktop-pet` 的业务逻辑，热更新只替换同一原生/模型布局的代码；气泡桥按能力检测，不再按桌宠版本号判定。
5. **音色、种子、采样参数、模型精度不变。** 精简的是运行组件与缓存，不是权重量化；已确认的 `soft-child-design-2` 与固定转录不能换。降精度会破坏已验收的听感。
6. **独显只能由用户显式选择。** 默认只自动选核显；没有核显时列出全部显卡并要求确认；非交互（AI 代跑）必须给出可复制的 `-DeviceName "显卡名称"` 命令，不允许自动回退到独显。
7. **重启前先问。** 扩展或引擎代码要重启 Coopanion 才生效，必须提示并等用户确认；未确认就延期，不擅自重启。
8. **更新只提示，用户主动才装。** 自动检查只做提示，下载、校验、备份、安装、回滚必须在用户点击后进行。
9. **不降级已安装的更新版本。** 市场版与本地版共用包名、World ID 和 Bot 数据目录，安装器按实际 `node_modules` 版本决定安装、更新、跳过，不能用旧完整包覆盖新版。
10. **报障需要当前用户授权。** 默认只在本机留报告；`autoSubmitIssues` 默认关闭。提交 Issue 必须有当前用户的明确授权且凭据可用，内容脱敏，不上传密钥、账号、聊天原文、完整配置或音频。
11. **魔搭只新增不覆盖。** 新版本用新文件名上传；覆盖旧文件会让仍在使用旧清单的用户校验失败。
12. **不关闭用户的程序、不修改个人配置。** 内存不够时提示用户腾出空间，不擅自结束游戏或其它进程。

## 6. 发布流程

### A. World 扩展（npm）

```powershell
cd world
npm test
npm pack
npm publish cortico-world-soft-voice-0.4.x.tgz --access public --registry https://registry.npmjs.org
npm view cortico-world-soft-voice versions dist-tags --registry https://registry.npmjs.org
```

发布需要 npm 双重验证：命令会打印一个网页授权地址，请在用户默认浏览器（**Firefox**）里完成，不要索取验证码或恢复码。

**关键经验：命令输出成功不等于发布成功。** 本仓库真的遇到过 `npm publish` 打印 `+ cortico-world-soft-voice@0.4.11` 且退出码 0，但 registry 仍停在 0.4.10。宣称发布前必须用 `npm view` 核对 `dist-tags.latest` 和版本列表；不一致时去 `%LOCALAPPDATA%\npm-cache\_logs\*-debug-0.log` 看 PUT 的真实状态码。

### B. GitHub Release（完整包 + 代码更新包）

```powershell
python scripts/build_portable.py            # 产出 .runtime/release-<版本>/
python scripts/build_update.py
python scripts/publish_release.py prepare --directory .runtime\release-0.5.x --notes <notes.md>
python scripts/publish_release.py publish --directory .runtime\release-0.5.x --notes <notes.md>
```

`prepare` 建草稿并上传资产，`publish` 变成正式发布。写 notes 时按用户能看懂的方式写：现象、根因、改了哪几处判定、验证了什么、限制是什么。

发布后核对：`releases/latest` 是否指向新版本、资产字节数是否等于 `portable-release.json` 的 `bytes`、匿名下载更新包并比对 `update-release.json` 里的 SHA256。

### C. 完整包内的 World 一致性

完整包和更新包都从**同一次真实 `npm pack` 的同一个 TGZ** 解出 World，并逐文件校验字节一致（`scripts/check_distribution.py`、`scripts/verify_install_channels.py`）。历史上出现过 7 个文本文件只差换行符，原因是打包前后工作区被 Git 规范化，所以打包与比对要在同一工作区状态下完成。

### D. 上架 Coopanion 官方市场

官方市场按 npm 的 `cortico-world` 关键字发现包，不是往官方仓库复制源码，依据是 [Cortico 扩展文档](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/extensions.md)。发布完 npm 后按关键字查询确认收录；索引未更新时可在桌宠里手动填写包名安装。`world/describe.json` 由 `world/scripts/describe.mjs` 生成，必须与代码和 `ENV_PROMPT.md` 模板逐字节对齐。

### E. 合并与推送

本机没有安装 `gh`，GitHub 的 MCP 集成**没有合并 PR 的权限**（会返回 403 `Resource not accessible by integration`）。合并做法是本地快进后直推：

```powershell
git switch main; git fetch origin; git merge --ff-only origin/main; git merge --ff-only release/0.5.x
git push origin main
```

## 7. 本机环境速查

| 位置 | 路径 |
| --- | --- |
| 仓库 | `E:\MC\gpt\coopanion-soft-voice` |
| Coopanion 应用 | `E:\MC\gpt\tools\coopanion\app`（0.2.1，未打包） |
| 桌宠包 | `...\app\resources\app\node_modules\cortico-world-desktop-pet`（0.2.0） |
| 扩展目录 | `...\app\data\extensions`（pnpm；`node_modules\cortico-world-soft-voice` 指向 `.pnpm` 虚拟 store；本地渠道副本为 `local-soft-voice`） |
| Bot 数据 | `...\app\data\home\companion\data\soft-voice`（`settings.json`、`runtime-profile.json`、`backups/`） |
| 已部署运行时 | `.runtime\release-unified-final\coopanion-local-voice-0.5.0-windows-x64`（内容已升到 0.5.5） |
| 构建产物 | `.runtime\build-<版本>`、`.runtime\release-<版本>` |
| 浏览器 | Firefox：`C:\Program Files\Mozilla Firefox\firefox.exe` |

扩展目录里的 `local-soft-voice` 与 pnpm 虚拟 store 是同一扩展的两份副本，改动要么同时更新、要么走 `scripts/install_world.py`；`package_target()` 会校验符号链接不越界，写入始终先写临时文件再原子替换，避免改坏 pnpm 的共享硬链接。

遗留未清理：`.runtime\release-0.5.6` 残留临时目录约 1.2 GB（删除被沙箱策略拦下）、`evidence/low-power-controls.png` 与 `evidence/voice-controls-final.jpg` 两个未跟踪文件。

## 8. 经验与踩过的坑

**判定要基于能力，不要基于版本号。** 气泡同步曾把桌宠版本写死成 0.1.4；Coopanion 0.2.1 把桌宠升到 0.2.0 后，一个功能完好的集成被判定成「缺少显示适配桥」。现在判据是钩子标记、浏览器端脚本、四个调用点是否齐全。同类问题要按“契约在、就在”的方式写。

**更新包里的新文件会被旧引擎拒绝。** 0.4.11–0.5.5 的安装拿不到 0.5.6 的更新，报 `Unsafe update member: world/describe.json`。原因是白名单在用户机器上那个引擎里，新版引擎加名字救不了旧安装。所以兼容性检查前移到构建期，并用冻结的历史白名单拦住不合规成员。

**“独显省内存”是误解。** 独显模式省下的是**共享显存**，系统 RAM 的占用和核显模式一样；3.25 GiB 的门槛依然适用，能下降的是独立显卡自己的专用显存。历史上核显测到的约 1 GiB 专用显存是 RTX 4050 的数据，不能外推到 Intel UHD。

**“模型只有几十 MB”也是误解。** 0.6B 是参数量：主模型解压后约 924 MiB，音频解码模型约 192 MiB。精简运行组件、推理缓存、模型权重是三个不同的体积指标，混在一起会得出错误的期望。

**首次出声慢可能只是一次性成本。** GTX 1660 报告里的首段 19.4 秒定位为着色器编译，稳态 RTF 0.44–0.58 且无欠载；核显暖机首次设备回调约 1.18–1.43 秒。不要把它当成稳态缺陷去改算法，先确认是否跨重启仍慢。

**界面没有反馈，等于功能不存在。** 用户明确要求过：开启语音时按钮本身要显示加载、同一个按钮点第二次结束、其它状态另处显示；设备选择后要回显“已选择”并跨页面保留；更新和部署要有阶段与百分比。这些都是验收项，不是装饰。

**版本滞后的清单无法引用自己。** 一键部署的 `deployment-manifest.js` 固定了完整包的字节数与 SHA256，而清单就在被固定的包里，改它就会改变包哈希。推进的路径是先把已冻结版本的相同字节同步到魔搭（新增文件），再在下一个 World 版本里指过去。

**长回复音色漂移要按文本复现来查。** 用户反馈“后半段变成熟女性”时，先核对是否回退到默认声源，实际没有；是分段导致的条件变化。修法是按自然边界分段（目标约 24 字、上限 32 字）、每段复用同一份完整 ICL 条件、逐次校验参考转录与特征哈希。

**打包产物要逐文件比对，不能只看版本号。** 同一版本在两个渠道里出现换行符差异，就是工作区被 Git 规范化导致的；比对必须在同一工作区状态下进行。

## 9. 验收标准

- 代码层面：`node --test world/test/*.test.js`、`python -m unittest discover -s tests`、`python scripts/check_distribution.py`，以及 `world` 目录下的 `npm pack --dry-run`。
- 运行时层面：在真实安装路径解压后跑 `scripts/verify_deployment.py`，要有**真实合成**（音频时长、`engineVersion`、欠载计数、连续播放），不能只看文件是否存在。
- 设备层面：核显与独显分别记录；无 GPU 的 CI 不能代替推理验证。改动内存相关代码必须附上有 GPU 机器的实测峰值。
- 听感层面：只有真人重新试听才能宣称听感验收；客观音高或频谱数据不能替代，也不能反推用户是否满意。
- 渠道层面：npm tarball 与完整包内嵌 tarball 逐文件一致；发布后 `npm view` 与 Release 资产都要核对。
- 报告实际版本、设备、结果、限制。**不要宣称所有硬件保证兼容**，不要把“文件存在”“`ok=true`”“模拟测试”当成性能或听感结论。

## 10. 未完成与下一步

来自 [PROJECT_STATUS.md](PROJECT_STATUS.md) 与 [OPTIMIZATION_PLAN.md](OPTIMIZATION_PLAN.md)，按接手时的优先级排列：

1. **确认契约 6 的实机效果**：更新扩展并重启后，扩展页不应再出现 world v5 警告。这次迁移仍没有在 0.2.1 实例里实机确认过。
2. **Issue #13（Intel UHD 慢速）**：已定位音频码预测阶段约占 57%，两种 Vulkan 路径探索均未采用。等目标设备用户回传诊断 ZIP，先排除负载波动再决定原生调度优化。
3. **Issue #15（GTX 1660 首段慢）**：等用户**重启电脑后**朗读第一句的结果，确认着色器磁盘缓存是否跨重启生效；只有每次重启都慢才需要做加载期预热。
4. **一键部署清单推进**：按上面的镜像同步顺序，把 `deployment-manifest.js` 指到新版本。
5. **原生工作进程替换默认后端**、**跨厂商自动调优**、**能效对照**、**RTX 5060 单独验收**：都仍在计划里，未验收不得写进已交付。
6. 清理 `.runtime` 里的历史临时目录，回收磁盘。

## 11. 与用户协作的约定

- 用简体中文沟通；代码、命令、标识符保持英文。结论先行，再给必要的证据。
- 版本、扩展名、界面文案由用户定调：不要软萌命名，扩展名要含功能关键词，当前名称是 **轻核语音 · Qwen3-TTS 超轻量高速语音引擎**，作者署名 **Asryto** 不省略。
- 用户要求“做完了再确认”：先完成代码、测试、实机核对，把可复核的结果摆出来，最后才问是否需要重启或发布。
- 需要用户在网页完成的操作（npm 双重验证、GitHub 设备码授权、魔搭登录）必须说明在哪一步、用哪个浏览器，且不要索取验证码或令牌。
- 用户机器内存经常紧张。需要腾内存时提示一次即可，之后继续做不依赖内存的工作；不要关闭用户的程序。

## 12. 接手第一个小时的清单

1. 读本页、`docs/PROJECT_STATUS.md`、`AGENTS.md`。
2. `git log --oneline -20` 看最近改动，`git status` 确认是否有未提交残留。
3. 跑一遍 `node --test world/test/*.test.js` 与 `python -m unittest discover -s tests`，确认基线干净。
4. 打开 `docs/INSTALL_CHANNELS.md` 与 `docs/PLAYBACK_AND_UPDATES.md`，确认两条渠道的规则你已经能复述。
5. 需要动本机时，先 `python scripts/install_world.py --extensions ... --bot ... --runtime ... --inspect` 看它打算做什么，再决定是否执行。
