# World npm 发布

包：`cortico-world-soft-voice` · 作者：Asryto · World API 5。

官方扩展市场从 npm 的 `cortico-world` 关键字发现包，不是向官方仓库复制源码。依据：[Cortico 扩展文档](https://github.com/Pal-AI-Lab/Cortico/blob/main/docs/extensions.md)。

## 首次发布

账号必须由发布者注册并验证邮箱；npm 正式发布要求双重验证或其规定的发布授权。见 [npm 官方发布说明](https://docs.npmjs.com/creating-and-publishing-unscoped-public-packages/)。密码和验证码在 npm 网页或终端输入，不提交到仓库。

```powershell
npm login --auth-type=web --browser=false --registry https://registry.npmjs.org
cd world
npm test
npm pack
npm publish cortico-world-soft-voice-0.3.11.tgz --access public --registry https://registry.npmjs.org
```

发布后用 `npm view cortico-world-soft-voice@0.3.11 version dist.integrity --registry https://registry.npmjs.org` 核对包。再按 `keywords:cortico-world` 查询并确认官方市场收录；索引未更新时可在桌宠手动填写包名安装。仅 dry-run 不算发布成功。

## 包和模型

npm 包含独立 World、面板与文档，不包含大型权重、Python 或用户配置。消费者推荐先运行 GitHub 完整安装包，再从市场安装扩展，保留 npm 更新能力。第一次 npm 注册和双重验证属于发布者要求，普通下载安装者不需要注册 npm 账号。

发布准备验证记录见 `evidence/2026-10-14-npm-market/check.json`。当前版本的候选 TGZ 与 SHA256 附于 GitHub v0.4.11 Release；它们提供下载，不表示已上架 npm。
