# PhysicalAI SO101 Lab — Golden Context Pack

**Context Pack：1.0.0 · 2026-09-18 · 项目阶段：M0–M2 已完成，M3/M4 部分完成，M5 软件就绪并等待有人在场采集。软件尚未发布。**

这是 Yang Liu 的 SO-ARM101 主从双臂、腕部/桌面双摄像头实验工作台。
优先复用官方 LeLab 图形工作台与 LeRobot 工具链，逐步完成配置、遥操作、示范采集、数据浏览、ACT 训练、真机评估与 PhysicalAI 研究关联。
它不是 Hugging Face LeRobot 的官方仓库或完整源码 fork，也不是重新实现机器人控制框架。

## 1. 放置位置与立即开始

将 ZIP **内的内容**解压到 `C:\Project\Physical_AI\Lerobot`，使本文件位于该目录根部，不要再套一层同名文件夹。
目标远端为 `https://github.com/sgyliu8/LeRobot.git`；父项目为 `C:\Project\Physical_AI`。
在 Codex 中直接打开子目录，粘贴 [完整启动提示词](docs/prompts/CODEX_START.md)。

离线检查本包只需 Python 标准库：

```powershell
Set-Location C:\Project\Physical_AI\Lerobot
python tools/validate_pack.py
```

这个命令不联网、不安装依赖、不初始化 Git、不打开摄像头或串口。
原始 pack 的 14 项回归结果见 [包验证报告](docs/reviews/PACK_VALIDATION.md)；当前候选共有 54 项项目 Python 回归、268 项固定 LeLab 回归和 15 项前端测试，包含真实编码 synthetic MP4/Parquet 的三回合软件闭环。fixture 不是实机证据，实时状态见 [HANDOFF](HANDOFF.md)。

固定上游、同步环境并启动本地工作台：

```powershell
Set-Location C:\Project\Physical_AI\Lerobot
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\bootstrap_upstream.ps1
uv sync --frozen
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 status
```

打开 `http://127.0.0.1:8000/`。日志和软件停止分别使用 `lab.ps1 logs`、`lab.ps1 stop`；停止入口只接受本项目记录的进程，并在硬件模式非空时拒绝终止。日常 `start` 不升级依赖、不重建前端、不下载模型、不连接机器人。

## 2. 当前事实

执行主机为 `YANGHOME`。Windows 当前枚举两个不同实例的 CH343：既有成功操作把 COM5 映射为 Yang101 leader、COM6 映射为 follower；COM1 是 ACPI legacy port，COM7 与 front 相机属于同一复合 USB 设备，均未被当作机械臂。用户已完成主从校准与 COM5→COM6 遥操作，本轮先备份现有配置、端口记录和两份校准，没有重复初始化、校准或移动机械臂。

保存配置保留既有字段：`arm` 是 wrist，`table_veiw` 是 front；当前请求值为 DSHOW 640×480/30 fps，Dataset FPS 候选为 15。此前双路 camera-only 采样和角色确认已通过；本轮两台相机又分别通过固定版官方 `OpenCVCamera` 的 640×480/30 短读并释放。重插/换序仍为 `NOT_RUN`。内嵌验证浏览器不提供 `navigator.mediaDevices`，所以记录窗口缩略图没有渲染；这不算 UI 预览 PASS，也不推翻独立 camera-only 结果。原始帧、完整设备 ID 和统计仅保存在忽略的 `.local/evidence/`，不进 Git。

M5 修复已贯通 UI profile 到真实 request/runtime：六个 SO101 关节限幅键及混合单位、Dataset FPS、H.264/yuv420p/PyAV 编码、本地无 HF 登录的新建/finalize/精确 ID resume；并分开处理 Accept、Timeout、Discard、Stop。官方 Dataset `action` 仍是 processed operator target，ignored sidecar 另存 requested/to-send/effective-sent/裁剪与实测、名义时间和主机时序。三回合真实采集尚未执行，不能标为 M5 complete。
详细观察、证据范围和待确认项见 [来源核查](docs/research/SOURCE_AUDIT.md)。

已安装的固定基线是 LeLab `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` 加受控补丁，以及 LeRobot v0.6.0 / `30da8e687a6dfc617fcd94afc367ac7071c376ce`。Python 为 3.12.13，完整解析保存在 `uv.lock`。具体身份、构建和限制见 [依赖合同](docs/DEPENDENCIES.md)。

## 3. 从哪里阅读

| 阅读目标 | 单一权威文件 |
|---|---|
| Codex 怎样执行、何时继续/停止 | [AGENTS.md](AGENTS.md) |
| 当前实际完成到哪里 | [HANDOFF.md](HANDOFF.md) |
| 项目要交付什么 | [需求](docs/REQUIREMENTS.md) |
| 软件边界与目录所有权 | [架构](docs/ARCHITECTURE.md) |
| 分阶段任务、退出条件、学习目标 | [路线图](docs/ROADMAP.md) |
| 复用界面、交互状态与信息布局 | [UI 规范](docs/UI_SPEC.md) |
| 图像、状态、动作、回合、模型身份 | [数据合同](docs/DATA_CONTRACTS.md) |
| 实测、负测试和证据标准 | [测试计划](docs/TEST_PLAN.md) |
| Git、验证、发布与 CI | [CI 策略](docs/CI_POLICY.md) |
| 硬件、权限、隐私、网络 | [安全与授权](docs/SECURITY.md) |
| 依赖、缓存和补丁 | [依赖合同](docs/DEPENDENCIES.md) |

根目录只保留四个 Markdown：README、AGENTS、HANDOFF、CHANGELOG。
不创建小写/大写两套同名文件，不复制第二份 requirements 或 roadmap。
其余内容按 operations / architecture / research / reviews / prompts 分层。

## 4. 成功的第一阶段

不是自制漂亮首页，而是：可重复启动官方工作台 → 设备身份明确 → 经现场确认的校准和小范围遥操作 → 双视角三个短回合 → 无机械运动的数据浏览。
先完成 M0–M3 的软件和相机工作；进入电机连接/配置或运动前完成 M4 现场准入。
M4 不能用截图、模拟设备、绿色图标或“USB 已连接”替代。

## 5. 包内是什么、不是什么

仓库内保留工程合同、可解析配置示例、来源登记、单一助手多角色评审记录、启动/恢复提示词、离线 validator、固定依赖锁、可重建补丁和本地服务入口。
`configs/lab.example.json` 是**本项目规范示例**，不是可直接提交到 LeLab API 的请求。
`configs/upstream-pins.json` 保存上游与补丁身份，`uv.lock` 是 M1 实际解析的依赖锁。
LeLab/LeRobot 已安装并运行；用户此前完成 Yang101 校准和受监督遥操作。本轮没有调用 `Robot.connect()`、校准、遥操作、录制、回放或真机 policy；真实三回合、训练和评估仍为 `NOT_RUN`。M5 使用三个实际只读子代理分别复核运行时、数据和 UI/交付，只有主代理修改代码和操作本地服务。

## 6. 操作原则

使用现成能力 → 正确配置 → 必要的薄封装 → 有复现证据的小补丁；最后才考虑新开发。
连接页面不是安全认证；3D 示意不是物理仿真；关节校准不是手眼标定；本地数据浏览不是动作重放。
默认不上传数据、不运行付费训练、不使用公司设备或数据、不更改父项目受控文件。
