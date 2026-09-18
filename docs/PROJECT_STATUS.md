# Project Status

本页只记录当前可用性和最近的验收边界，不保存逐版本开发流水账。

## 当前结论

**M5_DATA_READBACK_PASS / REAL_RESUME_NOT_RUN**

固定 LeLab/LeRobot 软件路径已经产出 7 个真实双视角回合。只读审计、官方 loader 与 CPU
DataLoader batch 均通过；数据技术门槛已经超过三个回合。7 个回合是在一个新建 session 中连续
采集，尚未用同一 ID 现场 resume，因此本页不把先前约定的 resume 程序门槛写成已完成。ACT
训练和策略评估仍未开始。

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
- 训练页默认自动选择当前 PyTorch 可用的 CUDA、MPS、XPU 或 CPU，并报告 NVIDIA/PyTorch mismatch。

### 真实数据读回

- 7 个 episode，canonical `episode_index` 为 0–6，共 3285 帧；
- Dataset FPS 15，两路 `arm` / `table_veiw` 均为 640×480 H.264/yuv420p；
- 两路每回合解码帧数与 Parquet 长度一致，PTS 单调，action/state 是有限六维向量；
- 官方 `LeRobotDataset` 通过明确的 PyAV 视频后端读到 7 回合、3285 帧，CPU DataLoader 同时返回两路图像与 action/state；
- 审计和 loader 前后文件 size/mtime/hash 清单不变，未 repair、删除或上传原始数据；
- 技术写盘成功不等于 7 次任务都成功，任务质量仍需操作者逐回合评价。

### 现场硬件

- SO-101 leader/follower 已完成一次受监督校准；
- 已验证 leader 与 follower 的有限遥操作链路；
- `arm` 与 `table_veiw` 两路相机角色已通过实际画面确认；
- 上述证据不等于当前会话仍可安全运动，重新执行前仍需当次现场检查。

## 尚未完成

- 使用现有精确 dataset ID 的真实 resume 追加路径；
- 对 7 个回合逐一记录任务成功/失败/中止的人工判定；
- ACT 训练、Replay、Inference 与有分母的真机评估；
- ROS 2、仿真和大型 VLA 不在当前闭环范围。

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

先在只读 Browse 中为 7 个回合记录任务成功/失败与中止判定。若确实还要继续采集，则在新的有人
现场会话中使用现有精确 dataset ID 和完全相同 profile 做一次真实 resume，再重复只读审计；不要
为了“补测试”而无目的驱动机械臂。进入 M6 前另行冻结数据分区、ACT smoke 配置、存储与算力预算。
