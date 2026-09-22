# Project Status

本页只记录当前可用性和最近的验收边界，不保存逐版本开发流水账。

## 当前结论

**M5_DATA_READBACK_PASS / ACT_CHECKPOINT_RESUME_PASS / MUJOCO_EPISODE_PLAYBACK_PASS / COLOR_SORTING_SOFTWARE_READY**

固定 LeLab/LeRobot 软件路径已经产出 7 个真实双视角回合。只读审计、官方 loader 与 CPU
DataLoader batch 均通过；数据技术门槛已经超过三个回合。7 个回合是在一个新建 session 中连续
采集，尚未用同一 ID 现场 resume，因此本页不把录制 resume 程序门槛写成已完成。ACT 已在 CPU
上完成 1-step smoke；另一个已有 step 1000 checkpoint 已完成完整状态续训到 1001/1002、两次
保存、Windows `last` junction 更新，以及 1002 的零新增步完整加载。完整基线和策略评估仍未运行。
三色分拣的 C0 配置、保存帧观察器、人工标签、session split、ACT 参数往返和本地结果卡已经实现；
没有采集该任务的真实 pilot，也没有训练或运行分拣策略。

## 已验证

### 软件与 UI

- 固定 Python、LeLab、LeRobot 与 `uv.lock` 可解析；
- 项目脚本可以 start、status、logs、stop，并核对进程归属；
- 服务只绑定 loopback，Host、Origin 与 WebSocket 来源受限制；
- 跨模式唯一 session/lease、stale cleanup 与 telemetry cache 有回归覆盖；
- UI recording profile 的 FPS、编码、六关节键/单位/限幅传入 runtime 并校验有限值；
- Accept、Timeout、Discard、Stop 具有独立状态语义；
- 合成 MP4/Parquet 可完成 create、finalize、Browse/audit、官方 loader、CPU batch 与精确 ID resume；
- 视频 EOF 不再用末帧无界替代，Browse/audit 保持只读。
- 数据浏览使用一基 Episode 1–N，同时明确保留零基 Dataset index 0–N-1；
- 训练页默认自动选择当前 PyTorch 可用的 CUDA、MPS、XPU 或 CPU，并报告 NVIDIA/PyTorch mismatch；
- UI、API、任务记录和 CLI 均固定训练视频后端为 PyAV；旧 `torchcodec` 请求迁移到 PyAV，
  无效后端被拒绝；
- 本地任务在创建任务记录和模型进程前由官方 Dataset loader 解码真实样本；任务元数据与日志
  固定写为 UTF-8，同时兼容读取旧 Windows ANSI 记录。
- Windows 本地 worker 由 PID、创建时间、可执行文件、完整命令行和随机任务 token 共同绑定；
  任务终态由持久 receipt 确认，无法读取身份的 `unknown` 不再被当作死亡或释放任务槽；
- checkpoint 的 model/full-resume 静态检查会解析 JSON 和 safetensors header。UI 只把 POST 成功
  称为“恢复任务已启动”，不会在优化器和随机状态真正加载前宣称恢复成功；
- 本地 `Auto` 在任务启动时用同一个 PyTorch 环境解析设备，并同时记录请求值与解析值；显式选择
  当前环境不可用的设备会在 Dataset preflight 前失败。
- ACT 的 `chunk_size` 与 `n_action_steps` 现在从 UI/request 进入 CLI，由固定 LeRobot parser 解析并
  写入实际 policy 配置；非 ACT/GR00T policy 不能携带这两个字段，GR00T 专用字段也不会传给 ACT；
- `color_sorting_v1` 公开 profile 保持实际颜色、尺寸、ROI 和 Dataset ID 为 unknown。纯帧 OpenCV
  观察器、人工 outcome 合同、session 级 split、train-only statistics 来源、本地摘要和 Browse 结果卡
  已有无硬件回归；任务文字和视觉标签明确不作为普通 ACT 条件。

### 真实数据读回

- 7 个 episode，canonical `episode_index` 为 0–6，共 3285 帧；
- Dataset FPS 15，两路 `arm` / `table_veiw` 均为 640×480 H.264/yuv420p；
- 两路每回合解码帧数与 Parquet 长度一致，PTS 单调，action/state 是有限六维向量；
- 官方 `LeRobotDataset` 通过明确的 PyAV 视频后端读到 7 回合、3285 帧，CPU DataLoader 同时返回两路图像与 action/state；
- 同一真实数据在本机 CPU 上完成 ACT 的 1-step、batch-size 1、零 worker smoke；训练进程正常
  退出，loss、learning rate 和 gradient norm 均为有限值；未保存 checkpoint，因此不构成基线模型验收；
- 一个已有 CPU checkpoint 从 global step 1000 恢复了模型、AdamW 优化器、随机状态和数据顺序，
  实际完成 step 1001 与 1002，分别保存完整 checkpoint；step 1002 随后再次加载模型、优化器和
  数据顺序并以 exit 0 结束。源 1000 的 11 个文件在恢复前后哈希一致；
- 审计和 loader 前后文件 size/mtime/hash 清单不变，未 repair、删除或上传原始数据；
- 技术写盘成功不等于 7 次任务都成功，任务质量仍需操作者逐回合评价。

### 现场硬件

- SO-101 leader/follower 已完成一次受监督校准；
- 已验证 leader 与 follower 的有限遥操作链路；
- `arm` 与 `table_veiw` 两路相机角色已通过实际画面确认；
- 上述证据不等于当前会话仍可安全运动，重新执行前仍需当次现场检查。

### 只读学习实验

- MuJoCo 在独立锁定环境中使用固定 Menagerie SO101 模型、简单桌面和方块；一个私有真实回合的
  547 帧 `observation.state` 已完成 headless FK，原生 viewer event loop 也完整退出；人工视觉检查为
  `NOT_RUN`。六轴无模型范围越界、无裁剪；
- Dataset action 只做有限值读取和哈希，保持 `processed_operator_target` 语义，没有当作实发或
  实测状态；gripper 0–100 只做 visual-only 数字角度映射，不解释为毫米；
- 回放前后源 Dataset 的 7 文件 manifest SHA-256 一致；派生报告和轨迹只写入忽略的 `.local`；
- ROS 2 的 JointState 轨迹、URDF package 本地准备器、限位审计和四终端启动顺序已经就绪。真实轨迹
  中有 2 帧超过该 URDF 的 Elbow 上限，默认阻断发布；只有显式 `--clip-urdf` 才产生标记过的视觉派生；
- 当前 WSL 没有 ROS 2、RViz 或 Jazzy 环境，因此 JointState、TF、RViz 和 rosbag2 实际运行均为
  `NOT_RUN`，没有自动安装系统软件；
- front 相机 ChArUco 几何实验已有输入与验收合同，但标记尺寸、内参、外参和新图像集尚未提供，
  公制位姿实验为 `NOT_RUN`。

## 尚未完成

- 使用现有精确 dataset ID 的真实 resume 追加路径；
- 对 7 个回合逐一记录任务成功/失败/中止的人工判定；
- 完整 ACT 基线、离线推理、Replay、Inference 与有分母的真机评估；
- 三色分拣真实 C1 pilot、人工数据质量审查、ACT 离线验证及 C1–C4 现场评价；
- ROS 2 运行时安装与只读 TF/RViz/bag 实测；front 相机几何标定；
- 动力学回放、碰撞验证、sim-to-real、大型 VLA、ROS 控制和真实策略运动均未运行。

## 真实采集候选 profile

| 字段 | 当前候选 | 是否冻结 |
|---|---|---|
| Dataset FPS | 15 Hz | 已冻结并实录 |
| `arm` | wrist，640×480，相机请求 30 Hz | 已冻结并实录 |
| `table_veiw` | front，640×480，相机请求 30 Hz | 已冻结并实录 |
| 编码 | H.264 / PyAV，`yuv420p`，CRF 23，GOP 2 | 已冻结并实录 |
| 六关节单位与限幅 | 五轴 degree；gripper `normalized_0_100` | 已冻结并审计 |
| 上传 | `push_to_hub=false` | 固定 |

正式创建数据集后，FPS、相机键、关节单位和标签语义不能在同一数据集内静默改变。

## 下一验收门槛

三色分拣的下一项 ready 工作是填写实际颜色、cube/bin 尺寸与 front ROI，并用保存帧验证观察阈值。
进入 C1 前集中确认现场人员、固定供电、Stop/独立断电、布局可达性与有限采集范围。另一个独立任务
仍是先在只读 Browse 中为既有 7 个回合记录任务成功/失败与中止判定。若确实还要继续采集，则在新的有人
现场会话中使用现有精确 dataset ID 和完全相同 profile 做一次真实 resume，再重复只读审计；不要
为了“补测试”而无目的驱动机械臂。下一项无需真机的 ready 实验是：在获准且已有的 Ubuntu 24.04
ROS 2 环境中运行只读 JointState → TF → RViz → rosbag2；若不安装 ROS，则等待已知尺寸 ChArUco
板、相机内参/外参输入后执行离线视觉几何。进入完整基线前仍需冻结数据分区、训练配置、checkpoint
存储与算力预算；checkpoint 恢复成功不证明模型质量或实用训练时长。
