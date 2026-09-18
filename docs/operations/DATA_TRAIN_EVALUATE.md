# Data → ACT → Evaluation Runbook

## 1. 最小任务定义

建议轻质易抓物体从标记起始区放进宽口容器。固定摄像头、物体类型和初始桌面条件；写出成功规则，例如物体完全进入目标容器且释放后保持稳定。
这是建议实验，不是已执行结果；换成用户实际物体时更新定义。

## 2. 三回合 smoke

检查两路 camera key/分辨率/请求 fps、主从 calibration、任务描述、output 根和 `push_to_hub=False`。本机既有键固定为 `arm`（wrist）和保留拼写的 `table_veiw`（front），不能在同一 dataset 中改名；Dataset FPS 与相机请求 FPS 是不同字段。

正式创建前冻结一个 recording profile：精确任务文字、Dataset FPS、两路 camera/backend/尺寸/请求 FPS、H.264/yuv420p/PyAV 参数，以及六个裸 SO101 key 的 `max_relative_target`。`shoulder_pan`、`shoulder_lift`、`elbow_flex`、`wrist_flex`、`wrist_roll` 单位是 degree，`gripper` 是 `normalized_0_100`。这些值限制相邻位置目标差，不是速度、碰撞或安全认证。

顺序固定为：

1. 新 dataset 只录一个完整短回合，正常 Accept/Stop 并等待 finalize；记录服务返回的**实际 dataset ID**。
2. 使用本地 Browse 和只读 audit 检查首/末帧、两路真实视频、Parquet、episode/task/index、状态与 action、结束原因和媒体边界；再用官方 `LeRobotDataset` 和 CPU DataLoader 读取至少一个 batch。
3. 只用第一次返回的精确 ID 和完全相同的 frozen profile 执行 official resume，再追加两个真实回合。不要手工拼文件、复制 fixture 或在同一 dataset 静默改配置。

Accept 保存当前回合；Timeout 有限结束并保留技术有效回合；Discard 是唯一清空并重录动作；Stop 不进入 reset/下一回合，非空 partial 作为 interrupted 保存。优先 LeLab 已有本地 browser；不上传 Hub 换取查看权限。

严格审计命令为 `uv run --frozen python -X utf8 tools/audit_dataset.py <actual-dataset-id> --camera arm --camera table_veiw`。默认只打印结果且必须保持数据 hash manifest 不变；若要保存报告，`--output` 只能指向忽略的 `.local/evidence/`。Browse/audit 不调用 repair 或 delete。

## 3. 采集扩展

M5通过后初始30–50条高质量示范只是起点，依据失败和覆盖决定增加。
记录variation范围；不能一边改相机安装/颜色处理/任务/末端工具一边把所有数据当同分布。
示范中的失败和恢复单独标注，不能偷偷删除所有不理想样本后宣称普适成功。

## 4. 训练前

按episode/session分区，不以相邻frame随机分区造成泄漏。
固定 LeRobot v0.6.0 recording path 的官方 Dataset `action` 是 processed operator target，不是 `send_action()` 返回的 effective-sent 值。训练标签保持官方语义；本地 ignored trace 另存 requested/to-send/effective-sent/裁剪和 pre-command measured state。未确定单位、键顺序或标签源就先修复，不盲训练。
Dataset `timestamp = frame_index / fps` 是名义时间；循环间隔与 host camera capture-completion/arrival 另存 sidecar，后者不是曝光时间。不能把两者混称为实测同步。
验证batch、dtype、channel order、camera keys、state order、normalisation、缺失值和视频可读性。
图像预处理要在训练和推理一致；不套用会改变任务线索的“美化”增强而不评价。

## 5. ACT第一版

使用固定LeRobot已有ACT，不重写网络。配置记录seed、步数、batch、图像大小、动作块长度、训练数据/模型身份和compute。
先一个短smoke确定数据与checkpoint链路，再正式训练。
当前CPU主机不自动承担长训练；明确GPU机器/云预算和数据去向后执行。公司机器和云资源不默认授权。
WANDB/Hub同步关闭或明确批准，不在错误排查时泄露token。

## 6. 离线输出检查

加载checkpoint与对应processor，运行独立离线obs，检查finite/shape/range/单位/键及耗时。
真实帧做offline inference不等于允许发送给电机。
比较请求目标、可能限幅目标和可获得的测量；不要声称模型直接控制力矩。

## 7. 真机评估

预先定义N、初始范围、任务timeout、人工干预和成功规则。建议小批10–20次作为学习统计，不声称工业可靠性。
记录所有开始的attempt；成功率 = 成功次数 / 已开始次数，同时单列failure、abort、intervention、timeout。
不能把人工帮助后的成功计作无干预成功。需要置信区间时明确小样本不确定性。
模型/阈值/配置变动后新建实验，而不是继续同一“固定评估”。

## 8. 第一项研究扩展

wrist-only / front-only / two-view观察消融具有直接硬件基础。
尽量使用同一原始数据的不同观测子集、相同数据分区和训练预算；评价条件随机/交替排序降低学习/环境漂移。
两相机更好是待测假设，不是结论；固定视角可能更稳定，腕部可能改善近接触信息，结果依赖任务。
未来SmolVLA进入同样的数据/评价合同；不凭论文数值保证此SO101的表现。
