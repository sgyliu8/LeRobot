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

## 训练设置与有效配置

可按 [README 的设置步骤](../README.md#模仿学习怎么设置) 找到界面字段。以下说明针对当前固定版本，
不是其它 LeRobot 版本或所有策略的通用默认值。

### 三种配置不要混在一起

| 配置来源 | 当前行为 |
|---|---|
| 新建普通 ACT 表单 | Local、Auto、10000 steps、batch 8、workers 4、seed 1000、log 250、save 1000；动作块留空使用上游 100/100 |
| 三色候选按钮 | 设置 task 为 `color_sorting_v1`、100 steps、batch 2、workers 0、save 100、validation 100、动作块 32/8，关闭图像增强 |
| 从 checkpoint Resume | 使用该存档的配置和完整训练状态；新表单默认值不替换保存配置，目标步数是全局总步数 |

三色按钮不选择 Dataset、不生成标签或 split，也不重置 Device、seed、Log Frequency、
Save Checkpoints、混合精度、优化器预设或 W&B。使用前应核对这些保留值。
CPU 首次 1–2 步检查是资源/读写试验，不是一次完整训练；100 步候选也不是效果保证。

### 优化器、学习率与实际生效值

保持 Advanced → Use Policy Training Preset 开启。当前固定 ACT 的预设为 AdamW，
learning rate `1e-5`、weight decay `1e-4`；图像骨干学习率也是 `1e-5`。
新表单的 Optimizer 下拉框虽然初始显示 Adam，但固定 LeRobot 在新训练配置校验时会用策略预设
替换优化器，因此不能只看这个下拉框。预设开启时手填 optimizer 字段也不代表它们最终生效。
这些值来自[固定上游 ACT 配置](https://github.com/huggingface/lerobot/blob/30da8e687a6dfc617fcd94afc367ac7071c376ce/src/lerobot/policies/act/configuration_act.py)。

若以后要手动调优化器，须提供完整且兼容的 optimizer / scheduler 配置并重新验证，
不能只关闭预设开关就假定表单已经足够。CPU 首次检查保持 Automatic Mixed Precision 关闭。
任务的最终依据是数字 checkpoint 中 `pretrained_model/train_config.json` 和
`pretrained_model/config.json`，而不是开始前表单的截图。三色 job 还保存
`training_split.json` 与 `training_data_receipt.json`，用于检查数据分区、统计来源与有效参数。

### 图像、数据与网络

- 本任务使用 `arm` 与 `table_veiw` 两路 RGB 和六维状态；训练目标保持官方 Dataset 的操作者目标语义。
- 640×480 是当前录制候选/已有数据尺寸，不是界面里另一个必须填写的训练尺寸，也不是保证吞吐的值。
  固定 ACT 的多路图像应具有相同形状；预处理和归一化必须与在线使用一致。
- 三色 task worker 只用训练回合聚合归一化统计，验证数据使用同一套训练统计，test 不进入训练或验证读取器。
  普通非 task 训练不会凭数据集名称自动启用这条冻结分区路径。
- Training 请求固定使用 PyAV 读取视频；它不是需要在表单里寻找的可选下拉框。缺帧/解码失败应先查数据，
  不在原件上自动补帧或删除。
- 新 ACT 使用 ResNet-18 公共图像预训练权重初始化骨干；本机缓存缺失时，首次创建模型可能联网下载。
  这不意味着下载了会分拣的机器人模型。Setup / 日常 Open 不会因此启动训练或下载该权重。
- Local、关闭 W&B、`policy.push_to_hub=false` 的路径不自动上传数据或模型。
  使用本地完整数据和已有权重缓存时不应为录制、浏览或保存而强制登录 Hub。

### 保存、续训与停止

开启 Save Checkpoints；Save Frequency 的单位是训练步，固定训练器也会在正常末步保存。
短训练应选择可观察的 Log Frequency，并预留存档磁盘空间。中途 Stop 不等于承诺保存一个新的
完整 checkpoint；先查看最后一个完整数字 step 目录，再决定从哪里恢复。

Resume 创建新的 job，恢复模型、processor、优化器、随机状态与数据顺序，不改写来源。
例如从 step 1000 继续到 1002，目标总步数为 1002。结构、数据内容或冻结分区发生变化时，
应建立新实验，不把它称为原实验的无变化续训。完整恢复验收见
[数据流程](DATA_WORKFLOW.md#checkpoint-与完整恢复)。

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
