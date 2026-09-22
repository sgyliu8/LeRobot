# Three-Color Sorting

`color_sorting_v1` 是一个分阶段的模仿学习任务：在有人监督的桌面工作区，把方块放进同色 bin。
首版复用一个 ACT、现有两路 RGB 与机器人状态；OpenCV 观察器只用于采集检查、标签和结果辅助核验，
不控制机器人，也不作为安全装置。

## 当前边界

| 阶段 | 场景 | 当前状态 |
|---|---|---|
| C0 | 配置、保存帧观察、标签、分区、UI 与报告 | 软件已提供；不代表真机成功 |
| C1 | 一个随机颜色方块、三个固定 bin | `NOT_RUN` |
| C2 | 少量分离方块、固定且可观察的选择规则 | `NOT_RUN` |
| C3 | 多方块有限整场 | `NOT_RUN` |
| C4 | bin 换位后的颜色匹配 | `NOT_RUN` |

C1 的结果不能外推为任意多物体能力。C2 可使用固定前视坐标中的“最左侧优先”等规则，但普通 ACT
不会读取外部 `selected_target_id`。若未来需要显式目标条件，必须同时改变训练输入和在线输入并验证
同一画面、不同目标确实产生可区分行为。

## 1. 建立本地任务 profile

公开示例故意不猜颜色、尺寸、ROI 或 Dataset ID：

```powershell
Copy-Item .\configs\tasks\color_sorting.example.json `
  .\configs\tasks\color_sorting.local.json
```

编辑被 Git 忽略的 `color_sorting.local.json`，在真实录制前填写：

- 三种实际颜色名称、每种打印件的稳定 instance ID 和基于保存帧测得的 OpenCV HSV 范围；
- cube 尺寸和三个 bin 的开口/高度；
- 固定布局 ID、front 画面中的 source、每个 bin interior/rim 及夹爪排除区的归一化 ROI；
- C1 的 `max_objects=1` 与 `selection_rule=single_visible_cube`；
- 本次录制 profile、校准和项目 commit 身份。

先检查 schema 和尚缺事实：

```powershell
uv run --frozen python -m so101_lab.color_sorting_cli validate-profile `
  .\configs\tasks\color_sorting.local.json --require-ready
```

新建录制时，LeLab 会返回带时间后缀的实际 Dataset ID。把该精确 ID 写回本地任务 profile，之后的
标签、分区、resume 和训练都使用它；不要自行推测或重命名。除这个首次返回的身份外，实物语义和
录制参数应在按下 Record 前冻结。

## 2. 用保存帧标定观察器

观察器接收现有图片数组，不创建 `VideoCapture`，因此不会抢占 LeLab 的 camera owner：

```powershell
uv run --frozen python -m so101_lab.color_sorting_cli observe-image `
  .\configs\tasks\color_sorting.local.json .\private\front-sample.png `
  --camera-key table_veiw --color-order BGR
```

输出包含 frame 身份、颜色、区域、bbox、中心、面积和有效性。以下情况返回 `unknown`，不能自动判成功：

- 帧陈旧、空图或无法分类的高饱和区域；
- 轮廓接触 ROI 边界、面积异常或可能粘连；
- cube 与 bin 内部同色，单一视角无法区分；
- 方块离开 source 或二维中心进入 bin，但没有稳定释放和人工核验。

bin rim 不参与 cube 搜索。实际阈值必须来自本机保存帧；示例中的空范围不是实物默认值。

## 3. 录制 C1 pilot

在 LeLab 的 Record 对话框选择 **Use color sorting v1**。该预设设置：

- 独立名称 `color_sorting_v1`；
- 固定任务文字 `Sort the visible cube into the bin with the same color.`；
- Dataset 15 Hz、3 个初始 pilot 回合；
- 保留 `arm` = wrist、`table_veiw` = front。

预设不会改变相机、校准、关节限幅或编码参数，也不会绕过现场检查。建议先每色 3–5 个短示范，
颜色与起始位置解耦，并覆盖不同打印实例；这是初始覆盖建议，不是成功保证。首次只录一个短回合，
finalize、Browse、只读审计和官方 loader 通过后，再用实际返回的同一 ID/profile 有目的追加。

## 4. 添加人工结果标签

每次尝试使用一个本地 JSON 对象。下面是字段示例，不是已经执行的结果：

```json
{
  "dataset_repo_id": "local/replace_with_actual_id",
  "session_id": "session-01",
  "scene_id": "scene-01",
  "layout_id": "replace_with_layout_id",
  "attempt_id": "attempt-01",
  "recording_profile_id": "replace_with_recording_profile_id",
  "calibration_id": "replace_with_calibration_id",
  "project_commit": "replace_with_40_character_commit",
  "policy_checkpoint_id": null,
  "episode_index": 0,
  "started": true,
  "cube_instance_id": "replace_with_instance_id",
  "cube_color_id": "color_a",
  "target_bin_color_id": "color_a",
  "actual_bin_color_id": "color_a",
  "initial_region": "left",
  "selection_rule": "single_visible_cube",
  "grasp_attempted": true,
  "grasp_succeeded": true,
  "placement_started": true,
  "released_and_stable": true,
  "observed_outcome": "unknown",
  "observer_frame_id": null,
  "observer_agreement": "unknown",
  "human_outcome": "success",
  "human_intervention": false,
  "end_reason": "normal"
}
```

把实际对象保存为被忽略的本地文件，然后追加：

```powershell
uv run --frozen python -m so101_lab.color_sorting_cli append-label `
  .\configs\tasks\color_sorting.local.json .\private\attempt.local.json
```

人工 `success` 只有在目标 bin 与实际 bin 一致、稳定释放且无人干预时才被接受。失败、中止、未知和
record 前拒绝的尝试都保留在分母中；标签必须与 profile 的 Dataset、布局、录制 profile、校准、commit、
checkpoint、颜色和打印实例一致，重复 attempt 或 episode 身份会被拒绝。

## 5. 冻结 split 并查看结果

单个 pilot session 可以先生成结果摘要；此命令不会伪造正式 split：

```powershell
uv run --frozen python -m so101_lab.color_sorting_cli summarize-labels `
  .\configs\tasks\color_sorting.local.json
```

收集到独立 session 后再冻结正式分区，不把同一 session 的相邻帧拆到不同集合。train、validation
和现场 test 都必须非空；明确列出 validation/test session，其余进入 train，归一化统计来源自动限制为
train episodes：

```powershell
uv run --frozen python -m so101_lab.color_sorting_cli audit-labels `
  .\configs\tasks\color_sorting.local.json `
  --validation-session session-validation `
  --test-session session-test
```

命令只在 `.local/evidence/recordings/color_sorting/` 写入哈希命名的 labels、summary 和 split 文件，
不修改 Dataset、视频或 Parquet。Browse 页面读取经过身份和字段检查的 summary，分别显示 started、
correct、failure、abort、unknown 与 preflight rejected；没有人工 summary 时明确显示未验证。

## 6. 训练候选

当前首个 ACT 候选把预测块与执行前缀分开：`chunk_size=32`、`n_action_steps=8`。它们是待离线延迟和
结果验证的候选，不是安全值。训练前必须先冻结 session split，并关闭 Hue、灰度和改变颜色类别的
增强。详细参数语义见 [Policies](POLICIES.md)。

真实 policy rollout 前还需要 checkpoint 完整加载、离线输出与耗时检查，以及新的有人现场批准。
新 episode、场景重置、故障或模式切换必须清空动作队列；计算不及时不能靠盲目补发旧动作掩盖。
