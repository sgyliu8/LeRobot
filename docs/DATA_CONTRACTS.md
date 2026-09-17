# Data Contracts — 复用 LeRobotDataset，显式记录语义

## 1. 哪个系统拥有哪类事实

LeRobotDataset v3 拥有训练用 frames、episodes、features、tasks 与 video index 的格式权威。
本项目只补可验证的实验上下文，不造替代数据集、重编号上游 episode 或默认一回合一个 MP4。
本地设备映射/实际 paths 放 `.local/`；示例配置在 `configs/`；公开摘要使用去标识后的逻辑 ID。

## 2. 身份链

```text
source revision + dependency lock
  → device role mapping + calibration identity + capture configuration
  → task/session/episode
  → dataset revision + split
  → policy/config/checkpoint
  → evaluation attempt + result
```

每次 run 有唯一 `run_id`，不重复使用已完成的数据目录做破坏性重录。
建议 ID 是时间+任务+递增序号，时间带时区；不要求为每个小记录建立企业级注册中心。
上游 `repo_id` 可作为本地 dataset 名称使用；仅设置它不等于已建 Hub 仓库或获准上传。

## 3. 观测字段

| 内容 | 必须解释 | 不可默认 |
|---|---|---|
| wrist/front RGB | key、顺序、shape、dtype、颜色通道、backend、实际分辨率 | BGR=RGB；两摄像头序号永不变 |
| joint state | 对应 motor、顺序、单位、norm mode、校准身份 | `.pos` 均为角度 |
| gripper | RANGE_0_100 或实测模式 | 0–100 是 degree、mm、力或开口百分比的公制测量 |
| timestamp | 所属时钟、采样/到达/写入来源、单位、缺失状态 | 软件到达时间就是 sensor exposure time |
| quality | 无效帧、读错误、重复/缺失的定义和检测方法 | 静止画面像素相同等于丢帧 |

实际 v0.6.0 follower 源码按 `use_degrees` 选择前五关节单位，gripper 始终 RANGE_0_100；默认 use_degrees=True，但记录中仍需核实实际配置。
未来接 ROS 2 时在 adapter 转换为其要求的单位并测试往返转换，不重写既有训练数据以迁就显示习惯。

## 4. 动作与物理执行

分别定义 `a_requested`（主臂或 policy 提议）、`a_sent`（限幅后发送的目标）、`q_measured`（之后读取的实际位置）。
LeRobot `send_action()` 返回可能限幅后的目标；调用方是否把这个返回值写入 Dataset 必须在固定 recording path 中核实。
**Sent 不等于 applied/mechanically achieved。**没有位置反馈/时间对应或力矩传感器，就不声称记录到真实执行轨迹/力。

动作合同至少含：关节顺序、绝对/增量目标、单位、normalisation/processor、control frequency 的来源、限制配置。
`max_relative_target` 限制目标与当前值的差；其效果依赖循环节奏，不构成速度上限、碰撞避免或安全认证。
夹爪与关节限制用逐关节配置，不能把同一个数当作统一物理单位。

## 5. 时间与双视角

保存原有帧索引/时间；附加 metadata 说明可测到哪些时钟。
实际能够获取时记录 camera arrival time、joint read time、loop time、write time；不可获取的 exposure timestamp 写 null / unavailable。
不要为填满 schema 人工生成看似精确的传感器时间。
首版接受明确标注的软时间关联，不宣称硬同步。需要时间精度的后续实验另设同步测量与误差预算。

## 6. 三层数据准入，避免过度防御

**D0 学习采集：** 必须知道软件/设备角色/字段/单位/任务/回合边界；允许尚无内外参和曝光时间，明确未知即可。
**D1 可训练：** D0 + 有效媒体/索引 + action 来源已核实 + consistent camera keys/shape + 合理 episode/session split + 数据可加载。
**D2 几何或时延研究：** 针对论断新增公制标定、外参、时钟/延迟测量和误差条件；缺失这些只阻止相关论断，不回溯性禁止普通行为克隆。

真实示范身份/动作单位/视角混乱是训练阻塞；没做 hand-eye 不是 RGB 模仿学习的通用阻塞。

## 7. 回合生命周期

每个回合记录任务、初始场景范围、采集会话、操作者匿名 ID、开始/结束/重置含义、取消/失败原因。
按 upstream metadata 确认 reset 帧是否写入，不能口头假定已排除。
Interrupted recording 保留文件；先复制/快照，再使用经过验证的官方修复流程。修复产生派生状态和报告，不覆盖原始证据而不留记录。
浏览器播放与 dataset decode 有分离测试；共享 MP4 内 seek 边界正确。

## 8. 数据分区和模型

同一 episode 不跨训练/验证集拆散相邻帧；优先按 session 分割以减少场景泄漏。
保留真正独立的最终 evaluation 条件；不在最终测试结果上反复选 checkpoint 后称无偏性能。
模型身份至少：policy family、代码/依赖、数据修订、训练配置/seed、checkpoint 文件、processor/normaliser、输入 key 和输出合同。
离线检查 finite values、shape、range 与推理耗时；通过不自动授予真机执行权限。

## 9. 本项目 sidecar

[实验模板](../templates/EXPERIMENT.md) 与 [评估模板](../templates/EVALUATION.md) 提供最小内容。
[run 示例](../configs/run.example.json) 是 sidecar，不是 upstream 文件替代。
禁止把 null 当作 0、unknown 当作 false、NOT_RUN 当作 FAIL。schema 的 nullable 字段保留信息不足语义。

## 10. 存储、备份与隐私

Git 不保存原始 MP4/Parquet、calibration、完整设备 serial/instance IDs、模型和家庭截图。
优先每次有效采集后保存配置+校准的本项目备份；数据根据容量做可读性检查与独立备份，不在每次运行扫描所有大文件计算哈希。
训练和评估边界固定一次 dataset/model identity；重大迁移或发布时才增加内容校验。
公开摘要去掉用户名、绝对目录、摄像头 serial、家庭画面和 token。

Sources: official Dataset v3, pinned SOFollower and LeLab recording/browsing code; see [source register](research/SOURCES.json)。
