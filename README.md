# PhysicalAI SO101 Lab — Golden Context Pack

**交付版本：1.0.0 · 2026-09-17 · 项目阶段：规划已交付，运行时尚未部署。**

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
本次实际执行的静态检查与 14 项回归测试结果见 [包验证报告](docs/reviews/PACK_VALIDATION.md)。
本包**没有**伪装成已完成的安装器、控制程序或已通过真机验收的软件。
Codex 必须按 roadmap 实施并验证，而不是把文档中的目标打勾。

## 2. 当前事实

用户报告：两只机械臂与两台摄像头已通过 USB 接入电脑。
本次 MCP 在 YangHome 上的枚举却只发现一个普通 COM1 和一台 UGREEN Camera 2K；未建立主从端口和双摄像头映射。
这两个观察并存，原因未确定。不能把 COM1 自动绑定成机器人，也不能推断用户没有连接硬件。
详细观察、证据范围和待确认项见 [来源核查](docs/research/SOURCE_AUDIT.md)。

已核实的上游候选：LeLab `6091a45811ef926a06b9b3622a9ab69fefb8bb7b`；它声明的 LeRobot v0.6.0 解析为 `30da8e687a6dfc617fcd94afc367ac7071c376ce`。
这是**候选部署基线，不是本机兼容性保证**。具体约束见 [依赖合同](docs/DEPENDENCIES.md)。

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

包内是完整工程合同、可解析配置示例、来源登记、五角色三轮评审结果、启动/恢复提示词及离线包验证器。
`configs/lab.example.json` 是**本项目规范示例**，不是可直接提交到 LeLab API 的请求。
`configs/upstream-pins.json` 是上游候选身份，不是 Python 依赖锁；`uv.lock` 由 M1 实际解析生成。
没有安装或运行 LeLab/LeRobot，没有打开设备，没有进行模型训练、真机试验或独立外部评审。
评审是同一助手执行的五专业视角三轮交叉审查，见 [评审记录](docs/reviews/THREE_ROUND_REVIEW.md)。

## 6. 操作原则

使用现成能力 → 正确配置 → 必要的薄封装 → 有复现证据的小补丁；最后才考虑新开发。
连接页面不是安全认证；3D 示意不是物理仿真；关节校准不是手眼标定；本地数据浏览不是动作重放。
默认不上传数据、不运行付费训练、不使用公司设备或数据、不更改父项目受控文件。
