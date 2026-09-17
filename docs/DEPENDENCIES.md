# Dependency and Upstream Contract

## 1. 已核查候选，不是“所有最新版”

| 组件 | 候选身份 | 处理 |
|---|---|---|
| LeLab | `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` | 固定 Git commit |
| LeRobot | tag v0.6.0 → `30da8e687a6dfc617fcd94afc367ac7071c376ce` | 遵循 LeLab 声明并核对 lock 中 resolved commit |
| Python | 3.12.x | M1 选择可用 patch 版，记录完整版本 |
| uv | 本机已存在，版本待 M1 核实 | 记录实际版本，不猜固定号 |
| Node | 初始不要求 | shipped frontend 可用时不构建前端；补 UI 才核查对应 Node/lock |
| GPU/Torch | CPU 首阶段；实际 torch 由依赖解析 | 不装所有 GPU extras，不提前承诺训练性能 |

精确身份保存在 [pins](../configs/upstream-pins.json)。pyproject 最低 Python >=3.12；某些说明文本中的旧 Python 要求不能覆盖安装清单。

## 2. 初始安装设计

由 Codex 在 M1 建立 project pyproject，project name 为 `physicalai-so101-lab`，Python 范围 `>=3.12,<3.13`，唯一主要依赖为固定 SHA 的 LeLab。
采用 uv project workflow：生成实际 lock，检查 transitive LeRobot resolved commit 与 pins 一致，再同步环境。
不预造 `uv.lock`、不声称本包已解决所有 Windows wheel 兼容。

建议实际执行序列（M0 完成且本轮软件授权生效之后）：

```powershell
uv --version
# 由 M1 创建准确的 pyproject.toml 后：
uv python install 3.12
uv lock
uv sync --frozen
uv run --frozen python -c "import importlib.metadata as m; print(m.version('LeLab')); print(m.version('lerobot'))"
```

安装前核对引导脚本的网络/缓存写入范围与可用磁盘；uv 的解释器/包缓存可位于用户工具目录，这是允许的共享工具缓存，不是允许修改父项目环境。
安装日志不应输出令牌、所有环境变量或用户名列表。安装结束后检查包路径和 entrypoints，而不只 version 字符串。
LeRobot 出现其他 commit 时停止版本替换，定位解析原因；不能用 --no-deps 强行掩盖不兼容。

## 3. 锁定与升级

锁定对象：LeLab/LeRobot commit、Python patch、uv 版本、全部解析依赖、Windows/driver 版本与后续 patch set。
不要把候选 pins JSON 当成完整依赖锁。
升级另开 branch：读 release/API diff → 无硬件 smoke → fixture data browse → 回放离线输入 → 需要时现场验证。
训练数据/校准/模型版本与运行软件分开管理；模型能加载不能证明 processor 兼容。

## 4. Windows 与相机

固定 LeLab recording path 为 Windows 选择 DirectShow，并支持每路 backend/fourcc 参数。
preview 和 recording 仍须核实到同一个物理相机，浏览器媒体 ID 与 cv2 index 不能直接互换。
相机 model/fps/format 由设备能力与实际捕获决定；网页商品规格不替代本机双路测试。
先避免 WSL/Docker 的 USB 转发复杂度；只有可复现的原生兼容阻塞才讨论迁移。

## 5. 缓存和存储

LeLab 固定配置代码直接使用 user-home 的 `.cache/huggingface/lerobot` 若干路径，不能假定设置 HF_HOME 完成全部隔离。
初期保留上游目录、选择本项目唯一 robot ID、创建 scoped backup、记录实际 paths；不删除全局缓存。
若现有 home calibration 和新设备身份冲突，先备份并请求实物对应确认，不盲目复用。
数据/模型容量从当前剩余空间出发测量；不要因缺少 GPU 先下载巨量 VLA 权重。

## 6. 必要补丁

只有复现的关键缺口才走 [ADR-002](architecture/ADR-002-PATCHES.md)。优先级：配置 > 同版本官方 CLI > 小源码补丁 > 新工具。
需补丁时使用 `_vendor/lelab` 固定 checkout；补丁 diff 与测试归本 repo，upstream checkout 被忽略。
环境切换到该受控 checkout 必须更新依赖声明/lock/源码路径证据，可重建；禁止编辑 site-packages 或复制一份不知来源的整个源码到根目录。
补丁完成后新机器应能 checkout 同 upstream + apply 同 patch + install 同锁，撤销时回到未改候选。

## 7. 许可

上游 LeLab/LeRobot 代码声明 Apache-2.0，保留 notice；数据、模型、图像/文档各自核查。
用户 repo 当前无已确认 licence。不自动赋予上游许可证于用户原创材料，不用“开源”推导可随意发布家庭视频。
来源与许可观察登记在 [SOURCES.json](research/SOURCES.json)，需要发布权重或数据时另加确切制品审核。
