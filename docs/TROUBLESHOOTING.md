# Troubleshooting

先停止受影响的模式，保存日志，再诊断。硬件异常时不要用重复点击或盲目重发来“试试看”。

## 常见问题

| 症状 | 先检查 | 安全处理 |
|---|---|---|
| 只看到 `COM1` | USB 线、供电、设备管理器、驱动、重新插入后的硬件 ID | 不把 `COM1` 猜成机械臂；保持端口为空直到身份确认 |
| 两臂端口变化 | 设备实例与实物标签，而不是旧 COM 数字 | 更新当次 UI 选择，不自动改 motor ID/baud |
| 相机缺失或画面重复 | 关闭占用进程，逐台打开，核对实际视角 | 释放句柄后再录制；不以 index 猜角色 |
| 相机帧率低于请求 | 实际协商参数、USB 带宽、codec、照明 | 先测量再冻结 profile，不伪报请求值为实测值 |
| `lelab` 无法导入 | `uv sync --frozen`、导入路径、`_vendor/lelab` | 不安装全局 LeLab/LeRobot 来掩盖来源错误 |
| 8000 端口已占用 | `lab.ps1 status` 与进程身份 | 不按端口盲杀；确认归属或先停止冲突应用 |
| 页面打开但硬件为空 | UI 启动本来不会自动连接设备 | 按 Hardware Setup 显式核对并进入对应模式 |
| Stop 被拒绝 | 当前是否有活动硬件 lease、页面是否陈旧 | 先用当前会话正常 Stop；必要时使用独立物理停止 |
| 机械臂突跳或方向异常 | 校准身份、端口角色、单位、关节映射 | 立即停止发送并隔离能量，不重发目标 |
| 录制反复重来 | Accept/Timeout/Discard/Stop 选择与日志 | Stop 应结束会话；不要用重启覆盖已接受数据 |
| Dataset 无法 resume | 使用的是否为第一次返回的准确 ID，profile 是否一致 | 不手工拼目录或在原数据上修补 metadata |
| 视频末尾缺帧 | 视频实际帧数、EOF、Dataset 窗口 | 保留失败证据；不要用最后一帧无限填补 |
| Browse 改变文件 | 比较审计前后 manifest/hash | 立即停止，保留原始数据副本并报告为失败 |

## 服务诊断

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lab.ps1 logs
```

日志位于忽略的 `.local` 运行目录。分享日志前删除用户名、绝对路径、设备序列号、家庭画面和凭据。

如果状态记录指向一个已经被复用的 PID，脚本应拒绝停止它。只有 PID、启动时间、命令行和项目根都
匹配时，才认为进程属于本项目。

## 数据诊断

```powershell
uv run --frozen python -X utf8 .\tools\audit_dataset.py <dataset-id> `
  --camera arm --camera table_veiw `
  --output .\.local\audits\<dataset-id>.json
```

审计失败时，保留报告与原数据。不要在 Browse/audit 阶段运行 repair、删除失败回合或手工合并文件。
技术上可以解码视频不等于任务成功；任务标签仍需由操作者判断。

## 重新构建

仅当固定 checkout 或 patch 有问题且确认本地 vendor 没有唯一修改时，才重新运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\bootstrap_upstream.ps1
uv sync --frozen
```

真实数据、校准和日志不属于 vendor 重建范围，不应为解决依赖问题而删除。
