# Policy Guide

本项目的第一个三色分拣 baseline 是 ACT。LeLab 负责本地工作台与任务生命周期，LeRobot 负责 Dataset、
policy、训练和推理；选择一个菜单项或保存一份配置不等于模型已训练或真机已验证。

## ACT 实际读取什么

当前固定 LeRobot 的普通 ACT 读取：

- `observation.images.arm` 与 `observation.images.table_veiw`；
- 六维机器人 state；
- 训练集中的官方 action。

Dataset 的 task 文字用于数据说明和未来可能的语言策略，不是当前 ACT 的语言输入。颜色观察器输出、
人工标签和外部 target ID 也不是 ACT 条件；它们用于覆盖检查与评估。

## 预测块与执行前缀

| 字段 | 含义 | 首个候选 |
|---|---|---|
| `policy.chunk_size` | 一次预测的动作序列长度 | 32 |
| `policy.n_action_steps` | 从该预测中执行的前缀长度 | 8 |

执行前缀必须大于 0 且不超过预测块。LeLab 对 ACT 和 GR00T 分别使用适用字段白名单：ACT 不再接受后
静默忽略这两个值，也不会收到 GR00T 专用参数。训练任务的 request、CLI argv、固定官方 parser 的
effective config 和保存的 policy 配置必须一致。

32/8 只是用于短离线实验的候选。最终值应结合当前设备的预处理、前向和后处理耗时、Dataset Hz、
动作更新节奏和有分母结果选择。旧 checkpoint 的结构参数不能随意改变后声称是完整 resume。

## 设备自动选择

Training 中的 `Auto` 在任务启动时查询同一个 Python/PyTorch 环境：优先当前实际可用的 CUDA，随后
是 MPS、XPU，最后回退 CPU。它不会安装 GPU runtime，也不会把操作系统看见显卡当作 PyTorch 可用。
任务记录同时保存 requested 与 resolved device。

CPU 可用于 loader、短训练、保存/重载与有限离线推理；不要无提示启动新的长时间训练。迁移到 GPU
电脑后重新按锁文件建环境，确认 `torch.cuda.is_available()`，再运行有界 smoke。

## 离线验收顺序

1. 冻结 train/validation/test session split，统计只来自 train；
2. 官方 loader 与 CPU DataLoader 读取两路 RGB、state 和 action；
3. 小 batch、短步数训练并保存完整 checkpoint；
4. 完整加载 model、optimizer、scheduler/随机状态和数据顺序；
5. 测量预处理、前向和后处理延迟；
6. 离线检查输出有限、关节顺序与单位匹配；
7. 经新的现场批准后才进入有限 rollout。

权重能加载、loss 较低或 synthetic fixture 通过都不是实物分拣成功。

## 运行时边界

- 每个新 episode、场景重置、故障和模式切换都清空 policy history 与动作队列；
- 没有新动作时不重发旧动作，超时后不盲目重试运动；
- rollout 继续使用唯一 hardware lease，不建立第二套串口或相机 owner；
- Stop 是软件停止，不是认证急停或 torque-off；
- 经典颜色观察器不直接产生关节目标，也不能认证碰撞安全。

Diffusion、π0 和大型视觉语言动作模型不属于首个 baseline。它们未来若进入实验，应分别报告实现、
依赖、权重、离线验证和真机验证状态，不能用“菜单中存在”代替证据。
