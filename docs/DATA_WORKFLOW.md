# Data Workflow

本项目使用官方 LeRobotDataset v3。真实数据闭环的目标不是“页面变绿”，而是得到可 finalize、
可只读审计、可由官方 loader 读取并能用精确身份继续追加的本地数据集。

字段与身份的稳定定义见 [Data Contracts](DATA_CONTRACTS.md)。

## 录制前冻结 profile

创建新数据集前，冻结并保存：

- 任务说明与成功标准；
- Dataset FPS；
- `arm` 与 `table_veiw` 的角色、分辨率和实际捕获率；
- 视频 codec、pixel format、CRF 和 GOP；
- leader/follower 配置与校准身份；
- 六个关节键、单位和有限的相对目标限制；
- action、state 和时序字段的语义；
- `push_to_hub=false`。

当前起点候选是 Dataset 15 Hz、两路 640×480 相机，以及现成 H.264/PyAV 路径
（`yuv420p`、CRF 23、GOP 2）。候选值必须经实际设备支持情况确认，正式创建数据集后不得在
同一 ID 内静默改变。

## 回合结束语义

| 操作 | 结果 |
|---|---|
| Accept | 保存当前回合，随后进入 reset/下一回合流程 |
| Timeout | 保存达到时限的当前回合；不会自动解释为任务成功 |
| Discard | 丢弃当前未接受回合，保留已接受回合并等待操作者决定 |
| Stop | 停止本次录制会话并保留已接受数据；不会伪装成 timeout 或触发无限重录 |

Discard 和 Stop 都不能删除已经 finalize 的历史数据。任务成功与技术上成功写盘是两个独立结论。

## 三回合闭环

### 第一阶段：新建一个回合

1. 使用新的 dataset ID 和冻结 profile 开始录制。
2. 由操作者移动 leader，录制一个短而完整的真实回合。
3. 正常结束并 Accept。
4. 停止会话并 finalize。
5. 确认两路视频、Parquet、metadata 和回合边界存在。

### 第二阶段：只读检查

使用第一次返回的准确 dataset ID：

```powershell
uv run --frozen python -X utf8 .\tools\audit_dataset.py <dataset-id> `
  --camera arm --camera table_veiw `
  --output .\.local\audits\<dataset-id>.json
```

审计会读取而不修复数据，并检查 profile、回合、视频窗口、帧、动作与时间语义。Browse/audit
不会自动补帧、删除文件或改变原始数据。短视频不能用最后一帧无限替代缺失帧。

还必须用官方本地 loader 打开同一数据集，并让 CPU DataLoader 成功产生一个 batch。

### 第三阶段：精确续录两个回合

1. 使用第一次录制返回的实际 dataset ID；不要手工拼目录或猜 repo ID。
2. 用同一 profile 进入官方 resume 路径。
3. 再录制并 Accept 两个真实回合。
4. 再次 finalize、只读审计，并确认累计恰好三个有效回合。

测试 fixture 或合成视频不能计入这三个真实回合。

## Action 语义

Dataset 中的官方 `action` 保持 LeRobot 的操作者目标语义。诊断 trace 另外区分：

- `requested`：处理前的操作者请求；
- `effective_sent`：经过 processor 与限制后实际提交给总线的目标；
- `measured_state_before_send`：发送前 worker 缓存的实测状态；
- `clipped`：是否以及在哪个关节发生裁剪。

这些字段不能互相冒充，也不能把 measured state 写成 action 标签。

## 时间语义

Dataset 名义时间轴是 `frame_index / dataset_fps`。它不等于：

- 控制循环实际周期；
- 相机帧到达主机的时间；
- 相机曝光时间；
- 指令真正到达电机的时间。

实测主机循环、相机到达和发送时间保存在本地 trace。设备不提供曝光时间时应记录为 unavailable，
不能从名义 FPS 推断。

## Browse、Replay 与训练

- **Browse / audit**：只读数据，不应连接机械臂。
- **Replay**：向 follower 发送历史 action，会产生运动。
- **Training**：读取已验收数据，不应隐式连接硬件或上传数据。

只有三个真实回合通过 finalize、视频/Parquet 审计和官方 loader 检查后，才进入 ACT 训练准备。
本项目默认不开启 Hugging Face Hub 上传、Weights & Biases 或云训练。
