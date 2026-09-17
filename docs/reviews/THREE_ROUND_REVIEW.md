# Three-round Review — Findings, challenges and dispositions

**Date:** 2026-09-17. **Execution:** single-assistant, five-role review. **Object:** this context pack and its integration plan.
Review结果只针对计划/文档，不是五位外部专家的投票或真实机器人验收。

## Round 1 — 问题定义和交付边界

### R1 机器人/机电

发现 R1-01 [Critical]：用户USB连接被过早理解为“可以开始自动调试所有按钮”；电机动力电源/安装/现场权限并未确认。
R4挑战：若对每一步都确认会违背先用起来。决定：软件A与相机B连续推进；电机C/D只在首次和关键变化时做有限session确认，不逐点击审批。
修改：SECURITY权限表、HARDWARE_BRINGUP、ROADMAP M4、AGENTS。验收：T-HW-01/02。状态：DOC_CLOSED / RUNTIME_PENDING。

### R2 软件架构

发现 R1-02 [Major]：新仓库叫LeRobot容易被误当官方源码fork，继而复制全部代码或新建UI。
R3挑战：实验台确需保存data/model身份。决定：子repo只保存integration与sidecar，官方Dataset和UI继续拥有其原功能；Python namespace使用so101_lab。
修改：ARCHITECTURE、ADR-001、REQUIREMENTS非目标。验收：T-ENV-01/T-PATCH-01。DOC_CLOSED。

### R3 数据/实验

发现 R1-03 [Major]：若把博士研究版所有calibration/time字段要求套到首个RGB示范，用户永远停在准备阶段。
R1挑战：不能牺牲动作单位与设备身份。决定：D0/D1/D2分层，动作单位/相机角色是基础，未做hand-eye只限制公制定位论断。
修改：DATA_CONTRACTS、M5/M6。验收：T-DATA-05。DOC_CLOSED / RUNTIME_PENDING。

### R4 Windows/UX

发现 R1-04 [Major]：先验假定两USB串口两相机在线，与当前YangHome OS枚举不符。
R5挑战：不得认定用户说错或推测他接在另一台。决定：并列用户报告与本次观察；M2验证主机/driver/数据线，禁止COM1默认绑定。
修改：HANDOFF、SOURCE_AUDIT、TROUBLESHOOTING、UI空状态。验收：T-DEV-01/T-CAM-01。DOC_CLOSED / RUNTIME_PENDING。

### R5 Git/交付

发现 R1-05 [Critical]：child尚无.git，在此目录直接Git写入会落到parent；parent尚未ignore子目录。
R2挑战：用户已固定nested路径，不应要求改成另一个目录。决定：own-root检查+parent local info/exclude单项例外；无submodule，无parent tracked修改。
修改：AGENTS、BOOTSTRAP、CI_POLICY、ADR-001。验收：T-GIT-01..03。DOC_CLOSED / RUNTIME_PENDING。

### Round 1 convergence

坚持LeLab/LeRobot主线；把首次交付定义为M0–M5，而不是“大而全平台”。
允许软件和相机先行，禁止未经确认的电机副作用。明确真正可执行的下一步是子Git和候选环境，而不是先写控制界面。

## Round 2 — 固定源码与失败情形挑战

### R1 机器人/机电

发现 R2-01 [Critical]：S07的connect会校准/configure，S03的teleoperate会写校准；因此“只连接读一眼”的自动检查可能有副作用。
并发现 R2-02 [Major]：S08的max_relative_target默认None，所选LeLab构造路径未传项目限制；只在example JSON写限制是假的保护。
R2挑战：不能因此重写驱动。决定：按副作用分类；首动前验证真实config，缺口用同版本CLI或小patch；目标差限制不宣传为速度/碰撞保护。
落点：SECURITY、DEPENDENCIES、ADR-002、M1/M4。验收：T-HW-01、T-OWN-01及config路径测试。DOC_CLOSED / RUNTIME_PENDING。

### R2 软件架构

发现 R2-03 [Major]：S02声明Python>=3.12/LeRobot v0.6.0，与父3.11环境及“最新都装”冲突；S05实际使用so_leader/so_follower的home路径。
R5挑战：virtualenv隔离不能防全局calibration覆盖。决定：固定两commit；M1生成真实lock；只使用本项目ID和scoped backup，不假设HF_HOME覆盖硬编码目录。
落点：DEPENDENCIES、ARCHITECTURE、pins、HANDOFF。验收：T-ENV-01/02。DOC_CLOSED / RUNTIME_PENDING。

### R3 数据/实验

发现 R2-04 [Major]：S07的gripper是归一化0–100，而S03可把数值作为角度显示；返回sent target也不是measured execution。
发现 R2-05 [Major]：共享MP4、episode边界、reset与中断finalize很容易被自制viewer误读。
R4挑战：不应立即重造浏览器。决定：沿用官方viewer，补单位/未知显示和边界fixture；固定record实际action写入路径需M5核实。
落点：DATA_CONTRACTS、UI_SPEC、DATA_TRAIN_EVALUATE、T-DATA系列。DOC_CLOSED / RUNTIME_PENDING。

### R4 Windows/UX

发现 R2-06 [Major]：S06 preview/record映射需要一致backend，浏览器deviceId与DSHOW index不等价；Computer Use会占Windows前台，可能抢唯一停止手段。
R1挑战：不能靠鼠标Stop当物理急停。决定：相机逐个确认且交接句柄；现场独立停止方式；纯GUI诊断与运动session分开，实际工具availability先检测。
落点：M3、UI_SPEC、COMPUTER_USE_DEBUGGING、SECURITY。验收：T-CAM-01..04/T-UI-02。DOC_CLOSED / RUNTIME_PENDING。

### R5 Git/安全交付

发现 R2-07 [Critical]：S25的停止candidate包含特定端口任意listener，不能无差别执行--stop。
发现 R2-08 [Major]：S04宽CORS/WS接入与局部active flags不能自动提供完整origin控制和跨模式互斥。
R2挑战：禁止扩张成企业鉴权/通用安全OS。决定：own-process lifecycle、无设备并发与来源负测试、必要时最小Origin/Host/WS和共享状态修补；不使用公网代理。
落点：ADR-002、ARCHITECTURE、TEST_PLAN、BOOTSTRAP。验收：T-WEB-01/T-OWN-01/02/T-STOP-01。DOC_CLOSED / RUNTIME_PENDING。

### Round 2 convergence

“复用现成”不等于“无条件信任默认值”。仅对影响本项目的确切缺口修补，其他功能直接使用。
静态风险与实际已复现故障分开；不把源码推断伪装成本机运行结果。

## Round 3 — 从下载到第一份真实数据的完整走查

### R1 机器人/机电

检查 R3-01 [Major]：文档某处若允许自动校准，而启动prompt只允许无设备，就会导致边界漂移。
R4提出恢复需求：同一session不应每次读状态再问。最终统一为A/B默认推进，C/D需要bounded bench confirmation；断连/故障/人员离开使旧motion权限失效。
审读AGENTS、SECURITY、M4、启动prompt后保留一致语义。验收仍在M4进行，不能用本文替代。DOC_CLOSED / RUNTIME_PENDING。

### R2 软件架构

检查 R3-02 [Major]：patch可能修在_vendor却运行site-packages旧包；unzip可多套一层目录；未来pyproject/uv.lock不应现在造假的安装成功。
R5挑战：缺少installer会不会不完整？决定：本交付是可执行工程合同，不是已开发runtime；prompt明确要求M1实际部署，不能停在第二份计划。
落点：README放置说明、DEPENDENCIES运行路径验证、BOOTSTRAP、prompt。DOC_CLOSED。

### R3 数据/实验

检查 R3-03 [Major]：3个短回合是pipe smoke，不是足够训练或成功率证据；30–50条建议也非保证。
R1挑战：评估中abort不可混成功。决定：分开M5/M6/M7；记录所有started attempts，干预/中止单列；CPU训练/推理能力实测。
落点：ROADMAP、templates、DATA_TRAIN_EVALUATE。DOC_CLOSED / RUNTIME_PENDING。

### R4 Windows/UX

检查 R3-04 [Major]：如果把线框当已实现界面或把所有按钮自动点击，视觉“完整性”反而导致误动。
R2挑战：需明确可复用的UI验收而不建新dashboard。决定：线框仅作信息需求；M1抓真实baseline；Browse/Replay、Update/Upload/Cloud各自分权限，不盲点击。
落点：UI_SPEC、COMPUTER_USE_DEBUGGING、T-UI/T-DATA。DOC_CLOSED / RUNTIME_PENDING。

### R5 交付/证据

检查 R3-05 [Major]：容易把五角色写成五个独立reviewer，或把静态validator写成全部软件通过；公开repo也可能泄露家庭图像。
R3挑战：严谨不应堆无用哈希和每次全套测试。决定：本次执行模式明确为单助手五角色；静态和runtime分报告；最小gate与一次发布checksum；raw data/local证据默认ignore。
落点：REVIEW_PROTOCOL、CI_POLICY、PACK_VALIDATION、README、最终prompt。DOC_CLOSED。

### Round 3 convergence

计划层关键矛盾已修正，没有留下会迫使Codex猜端口/电压/版本/权限的执行指令。
当前决议：**PACK_READY_FOR_BOOTSTRAP；RUNTIME_NOT_VALIDATED。**
这个结果不等于安全认证、五独立模型一致性，也不等于M0–M8完成。

## Consolidated residual register

| Residual | Why still open | Owner / gate |
|---|---|---|
| 实物与当前主机枚举不一致 | 不能由文件/网络确认USB实际归属 | 用户+Codex，M2 |
| 电源、固定、现场stop | 只能现场核对 | 用户，M4 |
| Windows依赖解析与GUI | 尚未部署 | Codex，M1 |
| 上游互斥/来源/停止实际行为 | 需fixture与UI回归 | Codex，M1 |
| 双相机backend/带宽/身份 | 需真实图像采集 | Codex+用户，M3 |
| 记录action语义与媒体完整 | 需源码路径审计+真实样本 | Codex，M5 |
| ACT训练/推理算力 | 尚无对应benchmark或训练资源决定 | 用户+Codex，M6 |
| 所有实际硬件安全/任务性能 | 仅规划，未执行 | 用户监督，M4/M7 |

软件问题按阶段验证；上述未知不阻止先完成独立环境和无设备UI工作。
