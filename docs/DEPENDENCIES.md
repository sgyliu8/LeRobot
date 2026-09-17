# Dependency and Upstream Contract

## 1. 已核查候选，不是“所有最新版”

| 组件 | 候选身份 | 处理 |
|---|---|---|
| LeLab | `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` | `_vendor/lelab` 固定 checkout + tracked patch |
| LeRobot | tag v0.6.0 → `30da8e687a6dfc617fcd94afc367ac7071c376ce` | 遵循 LeLab 声明并核对 lock 中 resolved commit |
| Python | 3.12.13 | uv 管理的独立项目环境 |
| uv | 0.12.4 | `uv.lock` 已解析并做第二环境重建 |
| Node/npm | v24.16.0 / 11.13.0 | 仅用于固定 LeLab frontend 的 `npm ci` / build / tests |
| GPU/Torch | Intel UHD；torch 2.11.0 | CPU 软件门槛；CUDA、训练性能 `NOT_RUN` |

精确身份保存在 [pins](../configs/upstream-pins.json)。pyproject 最低 Python >=3.12；某些说明文本中的旧 Python 要求不能覆盖安装清单。

## 2. 已实施的安装与重建

M1 已建立 `physicalai-so101-lab` project，Python 范围 `>=3.12,<3.13`。`pyproject.toml` 指向忽略的 `_vendor/lelab` editable checkout；`tools/bootstrap_upstream.ps1` 从准确 commit 重建该 checkout、应用 tracked patch 并构建 shipped frontend。完整依赖由 `uv.lock` 固定，LeRobot 的 direct URL metadata 解析为目标 commit。

新 checkout 的实际重建序列：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\bootstrap_upstream.ps1
uv sync --frozen
uv run --frozen python -c "import importlib.metadata as m; print(m.version('LeLab')); print(m.version('lerobot'))"
```

本机已用独立 `.venv-rebuild` 按锁完成一次 clean rebuild、114 包兼容性检查与当时 23 项测试，随后删除该临时环境；正式 `.venv` 保留。最终主环境候选包含 24 项测试。uv 的解释器/包缓存可位于用户工具目录，这是允许的共享工具缓存，不是允许修改父项目环境。
安装日志不应输出令牌、所有环境变量或用户名列表。安装结束后检查包路径和 entrypoints，而不只 version 字符串。
LeRobot 出现其他 commit 时停止版本替换，定位解析原因；不能用 --no-deps 强行掩盖不兼容。

patched frontend 的 `npm test` 为 6/6 PASS、受改文件 scoped ESLint PASS、production build PASS。上游全量 ESLint 仍有未触及的 6 errors / 13 warnings；`npm audit` 报告 1 high、2 moderate，未自动执行会改变依赖的 `npm audit fix`。

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

LeLab 固定配置代码直接使用 user-home 的 `.cache/huggingface/lerobot` 若干路径，不能假定设置 HF_HOME 完成全部隔离。本机会话核对的具体目录是 `calibration/teleoperators/so_leader`、`calibration/robots/so_follower`、`ports`、`saved_configs` 和 `robots`；首次 no-device UI 后它们均不存在，未创建、覆盖或清空任何既有校准/端口记录。
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
