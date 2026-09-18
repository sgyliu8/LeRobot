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

## Sidecar 与模板

- [`configs/run.example.json`](../configs/run.example.json)：最小 run sidecar 示例；
- [`schemas/run.schema.json`](../schemas/run.schema.json)：sidecar schema；
- [Experiment template](../templates/EXPERIMENT.md)：采集与训练记录；
- [Evaluation template](../templates/EVALUATION.md)：带完整分母的评估记录。

Sidecar 补充 Dataset 上下文，不替代上游文件。
