# Codex 项目启动提示词

将下面代码块中的全文作为第一次任务提交。工作目录必须直接打开 `C:\Project\Physical_AI\Lerobot`。
本提示词授权执行已定义的软件/观察工作，不自动授权未核实的电机配置或任意运动。

```text
你现在负责启动并交付我的 PhysicalAI SO101 Lab 项目。

【项目身份】
本地唯一工作根：C:\Project\Physical_AI\Lerobot
唯一目标remote：https://github.com/sgyliu8/LeRobot.git
父项目：C:\Project\Physical_AI，只读研究参考，不是本任务执行根。
我已把Golden Context Pack放进子目录。

硬件：Seeed Studio SO-ARM101一只leader、一只follower；一台装在follower腕部/夹爪附近的wrist相机；一台桌面支架上的front相机。
我报告这两臂两相机已通过USB接电脑。之前MCP在YangHome只枚举了ACPI COM1和一台UGREEN Camera 2K；这不是两臂两相机已经就绪的证据。请用本机会话重新核对主机和设备，而不是反复问我已经回答的硬件数量。

【任务目标】
复用官方LeLab界面和LeRobot驱动/数据/训练能力，完成实际部署与逐阶段验证。
不重写机器人UI、串口驱动、相机驱动、Dataset格式或训练器；不先安装ROS 2、仿真或大VLA。
本轮从M0开始，自动连续完成所有ready的软件/观察任务，优先做到M1官方本地UI可用与M2/M3设备/相机证据。
不要在生成第二份计划后停止。需要真正安装、启动、排错、验证并记录结果。

【首先阅读】
完全阅读并遵守：HANDOFF.md → AGENTS.md → docs/REQUIREMENTS.md → docs/ARCHITECTURE.md → docs/ROADMAP.md → docs/SECURITY.md → README.md → CHANGELOG.md最新相关记录。
本轮再读docs/DEPENDENCIES.md、docs/operations/BOOTSTRAP.md、docs/UI_SPEC.md、docs/TEST_PLAN.md、docs/CI_POLICY.md、docs/operations/COMPUTER_USE_DEBUGGING.md和docs/research/SOURCE_AUDIT.md。
进入相机/硬件/数据任务时按AGENTS的reading matrix追加必要文档，不每轮扫描整个父研究库。
列出本会话真正生效的AGENTS/global instructions，确认旧父项目M10任务没有被误续跑。

【M0：Git与父项目边界】
先检查目标目录自己的.git，以及git rev-parse --show-toplevel。没有子.git时，Git命令可能落到父repo，不许直接git add/commit。
检查父repo是否跟踪Lerobot路径。若未跟踪，允许你保留现有内容并幂等追加父.git/info/exclude中的/Lerobot/这一项；这是唯一允许的父metadata修改。
父受控文件、branch、remote、index、环境和已有服务都不改。若parent已tracked本目录，先报告具体冲突，等待迁移决定；独立软件分析可继续。
复核remote真实状态。此前它是公开空仓库、不是官方fork。若现在仍为空，建立干净的pack初始main提交并push，再开codex/bootstrap-so101-lab开展实现。
如果remote/本地已有工作，保留并合理协调；不force-push、不reset --hard、不删除后clone、不覆盖已有历史。
每次Git写操作确认根和remote。普通子repo提交/push可自主进行；不merge/release/tag/公开部署。

【M1：固定依赖，运行已有软件】
候选LeLab commit：6091a45811ef926a06b9b3622a9ab69fefb8bb7b。
其manifest声明Python>=3.12与LeRobot v0.6.0；该tag已解析为30da8e687a6dfc617fcd94afc367ac7071c376ce。
按configs/upstream-pins.json建立独立Python3.12环境，实际解析并保存uv.lock；核对真正导入的包文件、resolved commit和entrypoints。
不要安装进父环境，不全局pip，不把另一个最新版或Seeed旧fork命令混入。
本repo未来包名physicalai-so101-lab，namespace为so101_lab，不能创建遮蔽官方lerobot的包。
默认复用LeLab打包前端；确实需要源码小补丁才建立固定_vendor checkout与tracked patch，不编辑site-packages。
核对cache路径：候选使用home下so_leader/so_follower目录，不假设HF_HOME能隔离全部路径。只备份/修改属于本项目的ID，不清空他人cache。
首次软件启动先检查是否会隐式访问设备。状态检查和无设备tests不得调用带配置/校准副作用的Robot.connect。
服务只绑定loopback。8000被占用先识别归属，不能盲用lelab --stop或taskkill杀掉别的应用。
最少实现可靠start/status/logs/stop入口；日常start不升级依赖、不下载模型、不重新校准。

【源码缺口的处理】
依据SOURCE_AUDIT/ADR-002检查：运行config是否真接收到限制、跨模式原子互斥、非可信Origin/Host/WS、停止进程归属、gripper单位、陈旧/错误telemetry。
先用no-device fixture复现/验证，再做最小必要修补；不要因为这些问题重建整套框架或企业权限系统。
max_relative_target只是位置目标差约束，不可写成速度、碰撞或安全认证保证。

【设备与Computer Use调试】
你可以使用本会话可用的Browser/Computer Use验证真实页面、相机视角、设备管理器和GUI缺陷。
先核对工具权限和目标主机。local web优先Browser，原生GUI用Computer Use；工具不可用就明确报告并使用可行CLI/API，视觉项目标NOT_RUN，不伪造截图。
Windows前台操作不要与我抢鼠标键盘；关闭无关隐私窗口，不把密码/token/邮件/公司内容纳入截图。
不要自动点击所有按钮做覆盖：Calibrate/Teleoperate/Record/Replay/Inference和Update/Upload/Cloud/Delete的效果不同。
不会通过GUI操作ChatGPT、终端或安全/UAC提示来绕过工具审批，也不能替自己批准系统权限。
允许OS枚举、确认后的wrist/front相机预览、局部本地相机诊断。普通COM1、猜测的camera index都不是默认绑定。
先确认两台不同物理相机，记录role/backend/实际参数；preview与record交接句柄，不能多程序抢设备。

【硬件执行边界】
USB已连接不等于正确舵机供电。Robot.connect、calibrate和开始teleoperate可能写入电机配置，不作为“只读检测”。
进入C/D级前，请把无法从网络/源码获知的关键问题集中一次问我：实物套装/电源标签、固定与起始姿态、我是否在场、独立停止方式、批准的模式/范围。
不要重复问我机械臂和相机数量；不要猜电压/端口/是否已初始化。
如果上述已由我明确确认，可以在该有限session范围继续，不每次小动作都问；换模式、故障、重连、变更校准或我离开后重新确认。
不自动重写motor ID/baud/firmware；不强制重新标定；不未经批准重放或policy运行；不无人值守运动；不盲重发超时movement。
硬件缺事实只阻止相关动作，你继续软件/相机/fixture/文档工作，不让整个任务停在“等确认”。

【数据、费用与公开仓库】
本地优先，push_to_hub=False；不自动开启wandb、HF Jobs、云GPU、上传媒体或外部账户。
允许提交本子repo代码与脱敏文档；真实视频/Parquet/calibration/serial/logs/screenshots/模型/凭据不进Git。
不使用公司设备或数据。不把Computer Use截图送给模型与数据集未上传Hub混为“完全离线”。
后续M5直接使用官方Dataset v3。Browse不驱动电机，Replay会；二者不能混淆。

【验证与连续交付】
先运行python tools/validate_pack.py以及validator的unit tests，再按阶段建立真实的runtime tests。
每次改动跑最小相关gate，milestone候选跑一次该阶段完整gate；不每改MD计算sha256或重跑全部研究平台。
测试/仿真fixture必须明确标记；不把绿色UI、HTTP200或mock数据当真机结果。
按ROADMAP自动选择下一ready项；遇到真实阻塞给出证据并转入不依赖它的ready任务。

【本轮交付】
报告：起始/最终root/branch/HEAD/worktree/upstream；父例外写入；安装和resolved版本；已实现/修补文件；实际命令与PASS/FAIL/BLOCKED/NOT_RUN；真实UI与相机证据；原始数据去向；剩余硬件事实与下一个ready动作。
更新HANDOFF、CHANGELOG和对应ROADMAP状态，不复制多份同一权威。
可以创建或更新Draft PR，不合并。没有实际独立reviewer就写清单agent多角色，不冒充五专家。
优先交付可以真正打开和调试的官方工作台，不止一套新计划，也不夸称未经验证的“全部正常”。
```
