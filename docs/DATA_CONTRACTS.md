# Data Contracts

本项目复用官方 LeRobotDataset v3，不创建第二套训练数据格式。本页定义项目必须额外说明的身份、
动作和时间语义，使录制、审计、训练与评估使用同一解释。

## 权威边界

LeRobotDataset 拥有 frames、episodes、features、tasks、视频索引与 metadata 的格式权威。
本项目只增加：

- 非敏感配置示例；
- 每次录制冻结的 profile；
- 不改变官方 action 标签的本地诊断 trace；
- 实验与评估 sidecar；
- 只读完整性审计。

设备路径、序列号、校准、原始视频和完整 trace 保持本地，不进入 Git。

`episode_index` 是 Dataset 的零基稳定键，所以 7 个连续回合的合法索引是 `0..6`。面向人的 UI
另行派生一基 `episode_ordinal`（`1..7`）；分页、URL、API 和 Parquet 始终继续使用
`episode_index`，不能把显示序号写回数据身份。

## 身份链

```text
source commits + dependency lock
  → device roles + calibration identity + capture profile
  → task + session + episode
  → dataset ID + revision + split
  → policy + processor + checkpoint
  → evaluation attempt + result
```

每次 run 使用唯一 `run_id`。完成的数据目录不能被破坏性重录。`repo_id` 可以作为本地 dataset
身份；设置它不代表已创建 Hub 仓库，也不代表允许上传。

## 录制 profile

创建数据集前，profile 至少冻结：

| 类别 | 必需内容 |
|---|---|
| 任务 | 描述、成功标准、回合结束规则 |
| 软件 | 项目 commit、上游 commits、依赖锁 |
| 设备 | leader/follower 逻辑身份与校准身份 |
| 相机 | keys、角色、backend、实际 shape、实际捕获率 |
| 控制 | Dataset FPS、关节顺序、单位、processor、逐关节限制 |
| 视频 | codec、pixel format、CRF、GOP |
| 数据 | dataset ID、`video=true`、`push_to_hub=false` |

Resume 必须使用第一次返回的准确 dataset ID，并与原 profile 完全一致。

## 观测字段

| 内容 | 必须解释 | 不能默认 |
|---|---|---|
| RGB | key、shape、dtype、颜色通道、backend、实际参数 | BGR 等于 RGB；相机 index 永不变化 |
| Joint state | motor 对应、顺序、单位、normalisation、校准身份 | 所有 `.pos` 都是同一种物理单位 |
| Gripper | 配置模式与值域 | 0–100 自动代表 degree、mm、力或公制开度 |
| Timestamp | 时钟、来源、单位、缺失状态 | 主机到达时间等于 exposure time |
| Quality | 无效、缺失、重复的定义和检测方法 | 静止画面相同像素等于丢帧 |

缺失值保持 `null` / `UNKNOWN` / `NOT_RUN`，不能为了填满 schema 写成 0 或 false。

## Action 与实际执行

官方 Dataset `action` 保持经过 processor 的操作者目标语义。本地诊断 trace 另外记录：

- `requested`：处理前请求；
- `to_send`：processor 后准备发送的目标；
- `effective_sent`：限制后实际提交的目标；
- `measured_state_before_send`：发送前 worker cache 中的状态；
- `clipped`：逐关节裁剪结果。

Sent 不等于机械上已经实现。没有位置反馈、正确时间对应或力矩传感器时，不能声称记录了真实执行
轨迹或力。夹爪与其他关节也不能共用一个未注明单位的限制值。

## 时间语义

Dataset 名义时间保持 `frame_index / dataset_fps`。实测控制循环、相机到达、关节读取和发送时间
使用单独的单调主机时钟。无法取得相机曝光时间时写 unavailable，不从名义 FPS 推断。

首个行为克隆闭环可以使用明确标注的软时间关联。需要几何或延迟结论时，再增加相机标定、外参、
硬件时钟或误差预算；这些缺失只阻止对应论断。

## 回合生命周期

- Accept 保存当前非空回合。
- Timeout 保存达到时限的回合，但不自动判为任务成功。
- Discard 只清除当前尚未接受的 buffer。
- Stop 结束录制会话，不进入 reset 或下一回合；非空 partial 标为 interrupted，零帧不伪造回合。

Interrupted 数据必须保留。需要 repair 时先复制或快照，并使用经过验证的官方流程生成可追踪派生物。
Browse、dataset-info 与 `tools/audit_dataset.py` 保持只读；视频越过真实 EOF 时返回 missing/error，
不能用最后一帧无限填充。

Packed MP4 的 episode window 使用半开区间 `[from_timestamp, to_timestamp)`。容器 PTS 与 metadata
转成浮点后可能只差一个 ULP；审计与浏览共用微小边界容差，只用于识别同一个窗口端点，不用于
补帧、改视频或放宽帧数一致性要求。

## 数据准入

| 等级 | 用途 | 最低条件 |
|---|---|---|
| D0 学习采集 | 检查录制链路 | 软件/设备角色、字段、单位、任务和回合边界明确 |
| D1 可训练 | 行为克隆训练 | D0 + 媒体/索引有效、action 来源核实、keys/shape 一致、loader 可读 |
| D2 几何/时延 | 支持公制或同步论断 | D1 + 针对论断的标定、时钟、延迟和不确定度证据 |

同一 episode 不跨训练/验证集拆分相邻帧。优先按 session 分割，以降低场景泄漏。最终 evaluation
条件保持独立，不能反复查看后继续称为无偏评估。

## 只读回放派生轨迹

MuJoCo/ROS 使用的 JSONL 是忽略的派生物，不是 Dataset action 替代品。文件采用同目录临时文件后
原子发布，避免中断留下可被误读的短轨迹。每帧固定包含：

- `schema_version`、Dataset ID、episode、从 0 连续的 `frame_index` 和 `expected_frames`；
- 原回合 frame/timestamp/state/action arrays 的统一 SHA-256；
- 原始 `.pos` feature names 与逐轴 source units；
- 显式 model joint names；
- radians 位置与从零开始、严格递增的 Dataset 名义 timestamp；
- degrees→radians、gripper visual mapping、range clip 和边界调整的 transform provenance。

生成器验证回合帧号从 0 连续、timestamp 与 `frame_index / fps` 一致、state/action 均有限，并要求
冻结 profile 与 Dataset ID/FPS/单位/action semantics 一致。读取器要求最终行数等于
`expected_frames`，且所有行的身份、摘要与 transform 完全一致。报告分别记录原回合数组摘要和
JSONL 文件摘要。ROS 的 URDF limit clip 必须是显式、可报告的视觉派生；它不修改该 JSONL 或原
Dataset。

## Sidecar 与模板

### 三色分拣 sidecar

`color_sorting_v1` 的本地 sidecar 使用 `dataset_repo_id + session_id + attempt_id` 作为尝试身份，并把
canonical `episode_index` 与完整抓放一一关联。每条标签还必须与 profile 的 layout、recording profile、
calibration、project commit 和可选 policy checkpoint 身份一致。它另外记录 scene、打印件 instance、
cube/目标/实际 bin 颜色、初始区域、选择规则、抓取与稳定释放阶段、观察帧与一致性、人工干预、结束
原因，以及彼此独立的 observed 和 human outcome。

人工成功要求同色实际 bin、稳定释放且无人干预。失败、中止、未知与 record 前拒绝都保留在分母；
视觉 observed outcome 不能覆盖人工结果。pilot 可先生成摘要而不声称正式 split；正式
train/validation/test 按完整 session 分配且三个分区都非空，归一化统计只列 train episodes。标签、
摘要和 split manifest 使用 Dataset ID 的 SHA-256 作为本地文件名，存放在被
忽略的 recording evidence 目录；它们补充官方 Dataset v3，不改变 Parquet、视频或 episode metadata。

已开始但没有保存媒体的尝试保持 `started=true, episode_index=null`，计入中止/失败分母。
初始 ACT BC 的训练准入为人工 success 且无干预；其它训练 session 回合保留标签并列入排除清单。
schema 1.1 冻结 split 只允许相同内容幂等写入，不自动提升旧 1.0 的准入证据。
每个 task job 保存该 split 快照和 SHA-256；实际 train/validation 分别构造官方 Dataset，test 不加载。
worker 从 train episodes 的官方 Parquet metadata 聚合统计，只替换内存中的 stats，并保存内容摘要；
源 Dataset stats.json 不变。receipt 同时冻结实际使用的 metadata/data/video 相对文件名、大小与
SHA-256；统计不变的帧重排也会被检测。resume 使用父 job 的快照与内容/统计凭据，来源变化会拒绝
继续。训练后再追加 Dataset 可能改变共享文件的内容身份，应启动新实验而非静默 resume。

- [`configs/tasks/color_sorting.example.json`](../configs/tasks/color_sorting.example.json)：显式未配置的公开 profile；
- [Three-Color Sorting](TASK_COLOR_SORTING.md)：本地填写、标签与审查命令。

## 通用 Sidecar 与模板

- [`configs/run.example.json`](../configs/run.example.json)：最小 run sidecar 示例；
- [`schemas/run.schema.json`](../schemas/run.schema.json)：sidecar schema；
- [Experiment template](../templates/EXPERIMENT.md)：采集与训练记录；
- [Evaluation template](../templates/EVALUATION.md)：带完整分母的评估记录。

Sidecar 补充 Dataset 上下文，不替代上游文件。
