# Getting Started

本页覆盖安装、日常打开、更新和迁移。设备与运动条件另见 [Hardware](HARDWARE.md) 和
[Safety](SAFETY.md)。软件安装不会自动校准、下载模型或驱动机械臂。

## 前置条件

- Windows 11，PowerShell 5.1 或 7；
- Git、[uv](https://docs.astral.sh/uv/)（本项目验证版本 0.12.4）；
- Node.js 22.13+ 与 npm，建议 Node 24 LTS；
- Python 3.12，由 uv 为项目准备独立环境；
- 首次安装需要网络和足够磁盘空间；视频与 checkpoint 的空间另算。

## 首次安装

```powershell
git clone https://github.com/sgyliu8/LeRobot.git PhysicalAI-SO101-Lab
Set-Location .\PhysicalAI-SO101-Lab
.\Start-SO101-Lab.cmd setup
.\Start-SO101-Lab.cmd check
.\Start-SO101-Lab.cmd open
```

默认 clone 获取 main。尚未合并的功能应使用相应 PR 的 head branch，在 clone 时指定
`--branch <branch-name>`；不要以为打开旧 main 就已运行候选版本。当前边界见
[Project Status](PROJECT_STATUS.md#版本边界)。

Setup 从固定 commit 与唯一 tracked patch 重建 LeLab，使用 `npm ci` 构建前端，再执行
`uv sync --frozen` 安装本地 `.venv`。不全局 pip，不升级整个运行栈。
安装凭据保存在 `.local/runtime/install.json`，包含 patch、lock、实际源码和上游身份。

## 一个长期使用的快速入口

双击根目录 **Start-SO101-Lab.cmd**，按 Enter 或 1 打开。可以为这个文件创建 Windows 快捷方式；
快捷方式指向入口文件，而不是某个版本的 Python 或临时服务 PID。

| 菜单 | 命令 | 行为 |
|---|---|---|
| 1 / Enter | `open` | 验证安装、启动本项目服务、打开浏览器；不安装 |
| 2 | `setup` | 安装/重建当前检出的固定版本 |
| 3 | `update` | 更新当前 tracking branch，再执行 Setup |
| 4 | `check` | 查看 Git、导入/补丁身份与 CPU/GPU 能力 |
| 5 | `status` | 只读服务状态 |
| 6 | `logs` | 查看本项目日志 |
| 7 | `stop` | 只停止身份匹配且无活动任务的服务 |

命令形式为 `.\Start-SO101-Lab.cmd <命令>`。原有 `scripts/lab.ps1` 生命周期命令继续可用。
页面地址为 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。
8000 被其他程序占用时会拒绝启动并报告归属，不会强行停止别的服务。

## 更新与恢复

先在 UI 正常结束任务，再 Stop，随后选择 Update。它只接受本项目 origin、干净 worktree 和已有
origin upstream，执行 fast-forward；不自动切分支、解决冲突、丢弃修改或合并 PR。
日常 Open 不更新依赖。

安装与启动使用互斥锁。活动服务或当前目录的 Python 任务存在时拒绝维护。
补丁改变时先在旁边构建新 vendor，成功后把旧目录保留到 `.local/backups/`，包括其局部修改；
不直接覆盖它。构建失败时保留原目录和诊断，不假报成功。
恢复旧代码时检出明确的已知提交，再 Setup；不要只复制旧 `.venv` 或编辑 site-packages。

若安装中断，重新运行 Setup。若手工复制的环境解释器已损坏，先关闭相关进程，把该
`.venv` 改名保存，再 Setup。不要删除数据、校准或训练输出来“修安装”。

## CPU 与 GPU

Training 默认 `Auto`，在任务启动时按当前 PyTorch 可用能力选择 CUDA → MPS → XPU → CPU，
保存 `requested_device` 和 `resolved_device`。只读 API：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/system/cuda-status
```

操作系统看见显卡不代表 PyTorch 能用它。Windows 锁定环境可能是 CPU build；若
`gpu_present=true` 但 `cuda_available=false`，按
[PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)为该项目环境准备兼容构建。
随后重新 Check 和有界 smoke。Setup/Update 同步后必须再次检查，因为锁定同步可能恢复 CPU build。
自动检测不静默下载 GPU runtime 或大型模型；另一台 GPU 电脑必须完成本机验收。

## 迁移到另一台电脑

代码可 clone；私有数据不会随 GitHub 自动迁移。按照以下顺序操作：

1. 旧电脑结束录制/训练并备份，只复制已 finalize 的 Dataset 与完整 checkpoint/job 文件夹。
2. 新电脑 clone 需要的版本，运行 Setup → Check，不复制 `.venv`、`node_modules`、
   `_vendor` 或 `.local/runtime` 中的 PID/安装凭据。
3. 通过你自己的私有介质迁移下表内容，保留原件和文件摘要；不要上传到公开仓库。
4. 先 Browse、只读审计、官方 loader/CPU batch，再验证 checkpoint 完整恢复；不要直接运行策略。
5. 同一实物可以恢复其现有有效校准，但重新确认 USB 端口、两相机视角、供电和固定。
   新设备不能套用旧校准，也不要因为换电脑就自动重标定同一设备。

| 内容 | 位置与注意事项 |
|---|---|
| Dataset | 默认用户主目录的 `.cache/huggingface/lerobot/<owner>/<dataset>`，或显式 `HF_LEROBOT_HOME`；完整复制 meta/data/videos，保持精确 ID |
| 训练任务 | 默认该 cache 下 `outputs/train/<job-id>`，或 `LELAB_OUTPUT_ROOT`；复制整个 job，包括 run/checkpoints、配置、receipt 与日志 |
| 录制与三色 sidecar | 仓库 `.local/evidence/recordings/`；profile、标签、冻结 split 和统计身份不能丢失 |
| 本地配置 | `configs/**/*.local.json` 与你创建的私有输入；重新核对其中的路径 |
| 本项目设备校准 | 用户主目录 cache 的 `calibration/teleoperators/so_leader`、`calibration/robots/so_follower`，以及相应官方 SO101 校准；只恢复属于本项目的 ID |
| UI 设备记录 | 该 cache 的 `robots`、`saved_configs`、`ports`；旧端口与浏览器 camera ID 只能作为待复核信息 |

`HF_HOME` 不会统一隔离 LeLab 所有 home-relative 路径，不能只搬一个 HF_HOME 就宣称迁移完整。
恢复的本地 job 按新目录定位 checkpoint，不继续信任旧机器的 PID 或输出绝对路径。
旧 Dataset root 不存在时，Resume 在本机 cache 中按精确 ID 解析；找不到则阻断并提示恢复数据。
源 checkpoint 保持只读，续训进入新 job。复制时不依赖 `last` 链接：保留数字 step 目录并在 UI
选择实际 step，避免旧 junction 指向旧电脑。

“安装检查通过”不等于“另一台电脑完全验收”。新电脑还需真实 GPU/驱动、视频解码、checkpoint
加载和设备复核；先完成软件检查，再按 [Data Workflow](DATA_WORKFLOW.md) 进行有限验证。
