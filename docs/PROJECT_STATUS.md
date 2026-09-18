# Project Status

本页只记录当前可用性和最近的验收边界，不保存逐版本开发流水账。

## 当前结论

**M5_SOFTWARE_READY / AWAITING_ATTENDED_CAPTURE**

固定 LeLab/LeRobot 软件路径、无硬件回归与合成 Dataset v3 闭环已就绪。真实三回合数据闭环尚未
完成，因此不能标记 M5 complete，也不能进入 ACT 训练或策略评估。

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

### 现场硬件

- SO-101 leader/follower 已完成一次受监督校准；
- 已验证 leader 与 follower 的有限遥操作链路；
- `arm` 与 `table_veiw` 两路相机角色已通过实际画面确认；
- 上述证据不等于当前会话仍可安全运动，重新执行前仍需当次现场检查。

## 尚未完成

- 新 dataset ID 下的第一个真实短回合；
- 两路真实 MP4、Parquet、回合边界、action 与实测时序审计；
- 官方 loader 与 CPU DataLoader 对真实数据的读回；
- 使用精确 dataset ID resume 并追加两个真实回合；
- ACT 训练、Replay、Inference 与有分母的真机评估；
- ROS 2、仿真和大型 VLA 不在当前闭环范围。

## 真实采集候选 profile

| 字段 | 当前候选 | 是否冻结 |
|---|---|---|
| Dataset FPS | 15 Hz | 待现场确认 |
| `arm` | wrist，640×480 | 角色已确认；实际捕获率待测 |
| `table_veiw` | front，640×480 | 角色已确认；实际捕获率待测 |
| 编码 | H.264 / PyAV，`yuv420p`，CRF 23，GOP 2 | 待一次实录验证 |
| 六关节单位与限幅 | 必须全部有限且键完整 | 待本次 profile 冻结 |
| 上传 | `push_to_hub=false` | 固定 |

正式创建数据集后，FPS、相机键、关节单位和标签语义不能在同一数据集内静默改变。

## 下一验收门槛

有人现场、固定与供电仍正确、正常 Stop 和独立断电方法可用，并明确本次短任务与运动范围后：

1. 新建数据集并录制一个真实短回合；
2. finalize、双视频/Parquet 审计、官方 loader 和一个 CPU batch；
3. 使用实际 dataset ID 与同一 profile resume，再追加两个回合；
4. 对累计三个真实回合重复读回和质量检查。

只有这四步均有真实证据时，才将状态改为 M5 complete。
