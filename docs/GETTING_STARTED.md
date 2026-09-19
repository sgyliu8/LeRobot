# Getting Started

本页用于第一次安装、固定上游重建和日常启动。硬件连接与运动前置条件请另读
[Hardware Setup](HARDWARE.md) 和 [Safety](SAFETY.md)。

## 前置条件

- Windows 11 与 PowerShell 5.1 或 PowerShell 7
- Git
- [uv](https://docs.astral.sh/uv/) 0.12.4 或兼容版本
- Python 3.12；当前锁文件解析为 Python 3.12.13
- Node.js 与 npm；仅重建 LeLab 前端时使用

不要把依赖安装到系统 Python，也不要用另一个 LeRobot checkout 替换本项目的固定版本。

## 首次安装

```powershell
git clone https://github.com/sgyliu8/LeRobot.git PhysicalAI-SO101-Lab
Set-Location .\PhysicalAI-SO101-Lab

powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\bootstrap_upstream.ps1
uv sync --frozen
```

`bootstrap_upstream.ps1` 会：

1. 从 [`configs/upstream-pins.json`](../configs/upstream-pins.json) 读取固定 commit；
2. 在忽略的 `_vendor/lelab` 中准备 LeLab checkout；
3. 对干净上游应用仓库内 patch；
4. 安装并构建打包前端。

它是可重建入口，不是日常启动命令。脚本拒绝覆盖来源或状态不符合预期的 vendor 目录。

## 核对运行环境

```powershell
uv lock --check
uv run --frozen python -X utf8 -c "import lelab, lerobot; print(lelab.__file__); print(lerobot.__file__)"
uv run --frozen lelab --help
```

输出路径应来自本项目的 `.venv` 与 `_vendor/lelab`。不要从其他 Python 环境、全局
site-packages 或另一个 LeRobot 工作区导入。

## 计算设备自动识别

训练配置默认是 `Auto`。启动工作台后可以只读查询本环境的实际选择：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/system/cuda-status
```

`recommended_device` 会按 CUDA → MPS → XPU → CPU 选择。当前 Windows 锁定环境可能安装 CPU
版 PyTorch；即使另一台电脑有 NVIDIA GPU，只有 `cuda_available=true` 才代表这个 Python 环境
真的能使用 CUDA。若返回 `gpu_present=true` 且 `mismatch=true`，请按
[PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/)为项目环境安装与当前版本兼容的
CUDA build，然后重启并重新查询。项目不会在普通 start 时静默下载或替换大型 PyTorch 包。

## 启动与停止

首次安装完成后，最简单的入口是在仓库根目录双击 `Start-SO101-Lab.cmd`。它检查项目环境、
调用受控启动脚本，并在服务就绪后打开 loopback 页面；它不会安装或升级依赖。

也可以使用 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 status
```

浏览器打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。启动服务不会自动连接串口、
校准机械臂、下载模型或升级依赖。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 logs
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 stop
```

停止命令只处理项目记录且身份匹配的进程。若硬件模式仍在运行，先在 UI 中正常结束任务；
服务脚本不会用强制终止冒充安全停机。

## 日常使用

已经完成首次安装后，通常只需双击：

```powershell
.\Start-SO101-Lab.cmd
```

从 GitHub 拉取新提交后再运行 `uv sync --frozen`；只有固定 commit、patch 或前端依赖改变时，
才重新运行上游构建脚本。

## 本地生成内容

以下内容不会进入 Git：

- `.venv/`：项目 Python 环境；
- `_vendor/`：固定上游 checkout；
- `.local/`：PID、日志、私有 trace、审计输出和本机内部资料；
- 数据集、视频、校准、模型和训练输出。

删除或重建这些目录前，先确认其中没有唯一一份真实数据或仍在使用的校准。

## 下一步

安装完成后按以下顺序继续：

1. [Hardware Setup](HARDWARE.md)：确认端口、相机角色和现有校准；
2. [Safety](SAFETY.md)：确认有人现场、固定、供电和独立停止方式；
3. [Data Workflow](DATA_WORKFLOW.md)：冻结录制 profile，再创建真实数据集。
