# Cortico 官方契约与本地适配

核对日期：2026-10-13。实际部署验证目标：Coopanion **0.1.24** 所带 Cortico **World API 5**。
同时阅读以下官方教程，并以安装版实际源码核对接口；不假设 main 分支的新接口已被桌宠采用。

- [官方扩展教程](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/extensions.md)：ESM npm 包、WorldDefinition 默认导出、manifest、webUiClient/webUiStyle。
- [官方 World 生命周期和配置](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/worlds.md)：start/stop、WorldContext、persist。
- [官方控制台面板契约](https://github.com/Pal-AI-Lab/Cortico/blob/main/src/web/shared/client-panel.ts)：独立 panelId、invoke、root、signal、interval、ui。

## 本扩展采用的接口

`cortico.kind=world`、`api=6`、`displayName=轻核语音 · Qwen3-TTS 超轻量高速语音引擎`。保留 World ID `soft-voice` 和 npm 包名以避免已有配置失联。

World 契约 v6 把 WebUI 一侧的名字由 console 改成 webUi：实例接口 `console()` → `webUi()`，manifest 的 `consoleClient`/`consoleStyle` → `webUiClient`/`webUiStyle`，面板产物文件名随之改为 `webui-<版本>.js`/`.css`；`cortico.api` 必须等于本类的 6。0.4.9 及更早的包仍是 v5，靠框架过渡层加载并显示升级提示，下一个大版本起不再加载。契约升级清单见 [upgrading.md](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/upgrading.md)。

自描述 `describe.json` 由 `npm run describe` 从 `WorldDefinition.describe` 与 `role: 'envPrompt'` 的提示词模板生成；`world/test/contract.test.js` 在 CI 里核对它与代码一致，等价于官方 `pnpm check:extension` 对这三项的检查。
`console()` 声明 controls/status/config/voices 四个独立面板，每个面板有独立 mount，服务端严格分派方法。
面板仅写入 `ctx.root`，按钮使用 `ctx.ui.button`；请求通过 `ctx.invoke`，轮询通过 `ctx.interval`，自建监听绑定 `ctx.signal`。
图表为扩展自己的 SVG，无外部图表服务；只显示实际运行指标。CSS 通过官方 `webUiStyle` 声明，限定 `.lva`，不修改宿主页样式。
常规设置通过 `WorldContext.persist` 同步部署配置，兼容保留旧本地设置文件；音色资源和运行数据存储在 Bot 的 dataDir。

## 保留的兼容适配

`pet_say` 成功调用的朗读仍通过当前运行的 toolcalls.jsonl 适配器接入，只读已成功记录，不直接调用其他 World 工具，不写入 Persona/Memory。
官方 outputTap 是模型输出流接口，不能当成工具成功回执使用；当前不改为在未确认工具执行前朗读，避免把失败或取消的输出说出来。
这个日志格式依赖桌宠版本，因此保留解析/队列测试；桌宠升级后需检查实际成功回执。它不是官方承诺的跨 World TTS API。

## 开发与验收

运行 Python 测试、Node 扩展测试及 npm pack 内容检查；本机再验证四个面板、ZIP 导入、选择/切回、正常发声与停用释放。
CI 无核显不能替代本机推理。不会因 API 号相同就声称兼容所有未来版本。
# 语音能力环境提示词

本扩展通过官方 `World.console().promptDocs` 声明 `role: 'envPrompt'`，模板位于 `world/src/ENV_PROMPT.md`；`envPromptVars()` 提供 `softVoice.state`。Cortico 负责渲染并合入 Persona 系统前缀，不修改 Persona 人格或伪造用户消息。

模板说明 `pet_say` 的成功输出由本扩展自动朗读，以及静音、停用、内存不足、加载和故障状态。状态是前缀重建时的快照；设置改变后可使用官方“重新加载系统提示词”更新当前会话。不会为状态变化主动制造聊天或播报。

遵循官方模板覆盖顺序：扩展自带模板 → bot 包的 `worlds/soft-voice/ENV_PROMPT.md` → 部署目录同名文件。控制台编辑由 Cortico 保存为部署覆盖，升级不覆盖用户模板。参考 [官方 World 开发文档](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/worlds.md) 与 `src/core/prefix.ts`、`src/core/types.ts`。
