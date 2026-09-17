# Troubleshooting — 定位一层，不乱改多层

| 现象 | 先检查 | 不要做 |
|---|---|---|
| 只有COM1或没有USB serial | 执行主机、PnP、数据线、hub、控制板/driver身份 | 把COM1设follower；扫描所有端口发送舵机命令 |
| 只看到一个摄像头 | 是否同一主机、设备管理器、USB拓扑、另一应用占用 | 复制一路画面冒充两路；猜摄像头型号 |
| 相机预览和录制不是同一设备 | DSHOW/backend、index命名空间、角色映射 | 随机+1改index后直接收集训练数据 |
| 两路帧率下降 | USB带宽/format、CPU编码、fps/分辨率、磁盘 | 默认认为GPU故障；先装CUDA |
| LeLab import失败 | exact版本、Python范围、依赖锁、entrypoint | latest全量升级；--no-deps掩盖冲突 |
| UI可开但功能失败 | 控制台、backend路径、实际依赖版本、request schema | 从零换框架或重写前端 |
| 8000端口占用 | PID/创建时间/cwd/executable所属 | lelab --stop或taskkill杀掉任何占端口进程 |
| calibration找不到 | 实际so_leader/so_follower路径、本项目ID | 删除整个HF cache；照旧文档拼路径 |
| 机器人启动突然跳动 | 停止；校准/初姿态/方向/真实target限制 | 用更大速度/扭矩“顶过去” |
| 3D归零但机械臂未归零 | telemetry错误/数据陈旧/占位零值 | 把画面零当位置反馈 |
| 数据集本地打不开 | finalize/index、共享MP4边界、dataset存在路径 | 为排障先上传公网或删除目录 |
| replay与录像内容不一致 | mode、joint顺序、normaliser、发送语义 | 未监督反复replay找正确配置 |
| 模型loss下降但任务失败 | 数据覆盖、标签、相机、时延、分布偏移 | 换最大VLA当万能解决方案 |

## 分层策略

一次改变一个主要变量，记录前后差异；先用最小可复现的软件/fixture路径，不把带电机械运动作为第一排障手段。
接口不明时查固定版本源码并保存locator；不会从当前网页的滚动示例推导旧tag参数。
实物事实问一次集中问题；网络查不到的是私有硬件状态，不是多搜十篇文章就可以猜出的答案。
失败后保留数据和配置；不无限重试、不关闭安全软件、不运行随机驱动安装器。
