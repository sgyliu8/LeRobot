# Data → ACT → Evaluation Runbook

## 1. 最小任务定义

建议轻质易抓物体从标记起始区放进宽口容器。固定摄像头、物体类型和初始桌面条件；写出成功规则，例如物体完全进入目标容器且释放后保持稳定。
这是建议实验，不是已执行结果；换成用户实际物体时更新定义。

## 2. 三回合 smoke

检查两路camera key/分辨率/实际fps、主从calibration、任务描述、output根和push_to_hub=False。
先一个完整回合→停止→查看，然后再另外两个。不要先录大量数据再发现相机角色反了。
检查首/末帧、状态/action字段、reset是否进入episode、提前结束长度与媒体seek。
优先LeLab已有本地browser；不上传Hub换取查看权限。

## 3. 采集扩展

M5通过后初始30–50条高质量示范只是起点，依据失败和覆盖决定增加。
记录variation范围；不能一边改相机安装/颜色处理/任务/末端工具一边把所有数据当同分布。
示范中的失败和恢复单独标注，不能偷偷删除所有不理想样本后宣称普适成功。

## 4. 训练前

按episode/session分区，不以相邻frame随机分区造成泄漏。
核对实际LeRobot recording path的action semantics；未确定单位或标签源就先修复，不盲训练。
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
