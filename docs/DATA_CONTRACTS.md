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

分别定义 `a_requested`（主臂或 policy 提议）、`a_to_send`（processor 送给 robot 的目标）、`a_effective_sent`（`send_action()` 返回的限幅后目标）、`q_measured_pre_command`（该控制步发命令前的实测状态）。
固定 LeRobot v0.6.0 recording path 已核实：官方 Dataset v3 的 `action` 保存 processed operator target，而不是 `_sent_action` 返回值。SO101 Lab 保留这个官方训练标签语义，不静默改成限幅后值；本地 ignored trace 另记 `requested_processed_official_action`、`to_send`、`effective_sent`、逐键 `clipped` 和 `q_measured_pre_command`。
**Sent 不等于 applied/mechanically achieved。**没有位置反馈/时间对应或力矩传感器，就不声称记录到真实执行轨迹/力。

动作合同至少含：关节顺序、绝对/增量目标、单位、normalisation/processor、control frequency 的来源、限制配置。
`max_relative_target` 限制目标与当前值的差；其效果依赖循环节奏，不构成速度上限、碰撞避免或安全认证。
夹爪与关节限制用逐关节配置，不能把同一个数当作统一物理单位。

## 5. 时间与双视角

Dataset v3 的名义 `timestamp` 保持 `frame_index / dataset_fps`；它不是循环实测时间或相机曝光时间。附加 metadata 说明可测到哪些时钟。
实际能够获取时记录 camera arrival time、joint read time、loop time、write time；不可获取的 exposure timestamp 写 null / unavailable。
不要为填满 schema 人工生成看似精确的传感器时间。
首版接受明确标注的软时间关联，不宣称硬同步。需要时间精度的后续实验另设同步测量与误差预算。

## 6. 三层数据准入，避免过度防御

**D0 学习采集：** 必须知道软件/设备角色/字段/单位/任务/回合边界；允许尚无内外参和曝光时间，明确未知即可。
**D1 可训练：** D0 + 有效媒体/索引 + action 来源已核实 + consistent camera keys/shape + 合理 episode/session split + 数据可加载。
**D2 几何或时延研究：** 针对论断新增公制标定、外参、时钟/延迟测量和误差条件；缺失这些只阻止相关论断，不回溯性禁止普通行为克隆。

真实示范身份/动作单位/视角混乱是训练阻塞；没做 hand-eye 不是 RGB 模仿学习的通用阻塞。

## 7. 回合生命周期

每个回合记录任务、初始场景范围、采集会话、操作者匿名 ID、开始/结束/重置含义、取消/失败原因。SO101 Lab 的有限采集状态机固定为：Accept 保存当前非空回合；Timeout 保存并有限推进，不自动无限重录；Discard 是唯一清空当前未保存 buffer 的显式动作；Stop 不进入 reset/下一回合，非空 partial 保存为 interrupted，零帧则不伪造回合。
按 upstream metadata 确认 reset 帧是否写入，不能口头假定已排除。
Interrupted recording 保留文件；先复制/快照，再使用经过验证的官方修复流程。修复产生派生状态和报告，不覆盖原始证据而不留记录。
Browse、`/dataset-info` 和 `tools/audit_dataset.py` 是只读路径，不隐式调用 repair/delete。短视频目标越过物理 EOF 时返回 missing/error，不以最后一帧替代。浏览器播放与 dataset decode 有分离测试；共享 MP4 内 seek 边界正确。

## 8. 数据分区和模型

同一 episode 不跨训练/验证集拆散相邻帧；优先按 session 分割以减少场景泄漏。
保留真正独立的最终 evaluation 条件；不在最终测试结果上反复选 checkpoint 后称无偏性能。
模型身份至少：policy family、代码/依赖、数据修订、训练配置/seed、checkpoint 文件、processor/normaliser、输入 key 和输出合同。
离线检查 finite values、shape、range 与推理耗时；通过不自动授予真机执行权限。

## 9. 本项目 sidecar

[实验模板](../templates/EXPERIMENT.md) 与 [评估模板](../templates/EVALUATION.md) 提供最小内容。
[run 示例](../configs/run.example.json) 是 sidecar，不是 upstream 文件替代。
M5 recording profile v2 与逐帧 trace 位于 ignored `LELAB_RECORDING_EVIDENCE_ROOT`：profile 冻结 dataset ID、任务、`video=True`、`push_to_hub=False`、Dataset FPS、实际解析后的相机键/backend/参数、逐关节限幅与单位、H.264/PyAV 编码设置和机器人身份；resume 必须使用第一次返回的精确 dataset ID 且 profile 完全一致。Browse 只有在 profile schema 完整、任务与所有 indexed episodes 一致、每个 Parquet/action row 数和两路实际解码帧数都精确匹配 index 时才给出 `resume_ready`。trace 使用 `time.perf_counter` 记录循环间隔和 OpenCV host capture-completion/arrival-age；该相机时间不是 exposure timestamp。
禁止把 null 当作 0、unknown 当作 false、NOT_RUN 当作 FAIL。schema 的 nullable 字段保留信息不足语义。

## 10. 存储、备份与隐私

Git 不保存原始 MP4/Parquet、calibration、完整设备 serial/instance IDs、模型和家庭截图。
优先每次有效采集后保存配置+校准的本项目备份；数据根据容量做可读性检查与独立备份，不在每次运行扫描所有大文件计算哈希。
训练和评估边界固定一次 dataset/model identity；重大迁移或发布时才增加内容校验。
公开摘要去掉用户名、绝对目录、摄像头 serial、家庭画面和 token。

Sources: official Dataset v3, pinned SOFollower and LeLab recording/browsing code; see [source register](research/SOURCES.json)。
