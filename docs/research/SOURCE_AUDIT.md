# Source Audit and Initial Local State

**Observed:** 2026-09-17. **Purpose:** build an executable context pack, not certify hardware.
This audit combines the current conversation, read-only MCP inspections, official source code/documentation and three paper abstract checks.
No PDF was analysed or claimed deep-read in this preparation. No source code, library, simulator, model or robot was executed as part of upstream verification.

## 1. 本地与远端事实

用户声明拥有Seeed SO-ARM101 leader/follower及wrist/front两台相机，并已通过USB连接。
MCP连接YangHome，2026-09-17 21:35 BST左右进行Windows OS层查询：

| Observation | Result | Evidence limit |
|---|---|---|
| Child directory | `C:\Project\Physical_AI\Lerobot`存在，目录列表为空，无own .git | 解压/后续操作后须复核 |
| Parent Git | m10分支、HEAD 14bff36…、无受控改动输出 | 不表示父全部功能重新验证 |
| Parent child paths | ls-files无结果，check-ignore无匹配 | 初始需要local exclusion |
| Target remote | public、fork=false、size=0、branches=[] | 元数据/refs观察，不替代执行时复核 |
| Windows | 11 Pro；i5-12450H；15.8 GB RAM；Intel UHD Graphics | 未做负载/推理基准 |
| Disk | C: 53.4 GB free | 仅该次快照 |
| SerialPort / Ports | 一个ACPI Communications Port (COM1) | 不能绑定为机械臂 |
| Camera / Image | 一台UGREEN Camera 2K | 未打开图像，不确认它就是用户两相机之一 |
| Required hardware | 未建立两USB motorbus与两相机角色 | 不推断用户未连接；主机/driver/USB待核实 |

这些查询没有打开串口、调用Robot.connect或拍摄相机。没有修改父/子repository，也没有安装依赖。
仅对本任务相关设备进行定向枚举；其他设备问题不纳入本项目排障范围。

## 2. 上游版本与实质发现

| Finding | Evidence | Design consequence |
|---|---|---|
| LeLab候选commit固定，依赖LeRobot v0.6.0且Python>=3.12 | S02/S23/S24 | 独立3.12环境，真实lock验证，不混latest |
| 当前标定路径使用so_leader/so_follower | S05 | 不复用旧文档的so101_*路径猜测；home cache单独识别 |
| Robot.connect可触发校准及configure | S07 | 不纳入无副作用healthcheck |
| Teleoperate起始显式写calibration并configure | S03 | 开始按钮属于硬件配置/动作边界 |
| gripper归一化0–100，前五关节依据use_degrees | S07/S08 | 单位与动画分开，不把所有.pos当degree |
| max_relative_target默认None；选读LeLab构造路径未传此值 | S03/S06/S08 | 首动前核实限制真正进入运行config；需要时小patch |
| active flags存在局部保护，但未证明跨模块原子性 | S03/S06 | fixture并发测试后决定最小共享锁，不能说已有或完全没有全局保护 |
| server含宽CORS与WS accept路径 | S04 | loopback非完整鉴权，测写入/WS来源限制 |
| launcher按特定端口监听者也筛PID | S25 | 不对任意占端口服务执行--stop；own-process限定 |
| Recording默认push_to_hub=False，Windows选DSHOW | S06 | 保留本地默认，验证preview/record身份一致 |
| v3可共享底层媒体文件 | S09 | 用metadata定位episode，不假定一回合一MP4 |

这是对明确文件片段的审查，不是宣称读完LeLab/LeRobot所有实现、所有API或所有测试。
例如dataset browsing的本机正确性、录制action存储语义、全局互斥和异常停止仍是M1/M5运行验证任务。

## 3. 为什么不把所有未知都做成“继续全网搜索”

软件问题查固定源码/官方文档；实物型号、适配器输出、安装方向和现场人员只能靠用户实物确认或本机检查。
公共教程不能提供用户设备的唯一serial、真实供电或已存在标定状态。这里保留UNKNOWN，而不是生成看似完整的参数。
对版本性疑问优先manifest和实际源码，不把README、旧论坛或不同fork命令拼成一套运行环境。

## 4. 阅读深度与停止准则

已覆盖本轮决定所需的候选依赖、设备配置副作用、相机后端、缓存、目标单位、启动/停止、数据格式、Codex指令与GUI权限。
未做全网穷尽、递归所有外链、论文PDF深读、仿真benchmark、上游test suite或实机validation。
ACT/LeRobot/SmolVLA论文只是学习路线依据，不用它们替代准确API或承诺本机性能。
达到“可以写明M0–M5步骤、验收和阻塞条件”的证据范围后停止扩散；后续问题按实际失败检索。

## 5. 来源使用规则

[SOURCES.json](SOURCES.json)保存25个可追溯入口、观察日期、读取深度和边界。
Git SHA冻结代码身份；滚动docs仅作导航/解释；论文abstract不升级为deep-read；同项目README和docs不是独立性能验证。
日志/screenshot/硬件测量未执行时持续标NOT_RUN。
