# AI 部署入口

作者 Asryto。部署先读 `docs/AI_DEPLOYMENT.md`。默认免编译完整包，入口 `scripts/deploy.ps1`；不要让普通用户安装编译工具或重新下载完整模型再裁剪。

- 从 `portable-release.json` 固定 URL 下载并核对 SHA256，或使用同版本 Release ZIP。包内 `install.cmd` / `scripts/install-portable.ps1` 自带 Python、小模型和引擎。安装自动寻找 Coopanion，找不到或多副本再选择。
- Windows x64、厂商 Vulkan 驱动、核显、加载前至少 3 GiB 可用 RAM；自动恢复线 3.5 GiB。只有一块核显时自动选择，多块需明确，不回退独显。不降低保护线，不关闭游戏。
- `-RuntimeOnly` 先验证运行时；必须检查真实合成和静音设备测试结果。文件存在不代表连接成功，不能把无 GPU CI 当推理验证。
- 接入用户自己的 Coopanion/Bot，保留个人配置和备份；只在接入需要时正常退出并重启桌宠。不能改聊天模型账号、桌宠本体业务逻辑或开机自启。
- 保留已确认音色、种子、采样参数；气泡同步首次默认开启，保留用户的选择。不能自动换声或使用云服务。
- `evidence` 含历史实测路径，不是安装依赖。禁止复制作者虚拟环境、个人配置、日志或密钥。所有运行路径必须由安装器在部署机器生成。
- 源码重建仅用于开发者或明确需要的备用路线：`scripts/deploy-source.ps1`，Python 3.10–3.12 x64 和 Git，初次提取需 4 GiB；旧 CUDA `setup.ps1` 不是默认路线。
- 修改代码保持可移植，做相关验证。原生补丁改动需真实构建。报告实际版本、设备、结果和限制，不宣称所有硬件保证兼容。
