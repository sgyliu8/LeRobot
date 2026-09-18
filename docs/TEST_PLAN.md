# Test Plan — 测什么就只宣称什么

## 1. 分层证据

P0 文档/配置静态检查；P1 无硬件代码/接口测试；P2 本机 GUI 与相机；P3 现场主从/记录；P4 训练/离线推理；P5 真机任务评估。
这里 P0–P5 是测试层，不是问题严重度；评审问题使用 Critical/Major/Minor，避免混淆。
通过某层不能自动升级到下一层。

## 2. 可追溯验收矩阵

| Test ID | 方法 | 通过条件 | 关联需求 |
|---|---|---|---|
| T-GIT-01 | own .git / toplevel / remote | 精确子根与用户 remote | REQ-001 |
| T-GIT-02 | parent ls-files / check-ignore / diff | 子目录未被父跟踪；父受控 diff 不变 | REQ-001 |
| T-GIT-03 | remote refs / baseline workflow | 无覆盖已有历史，无意外 parent commit | REQ-001 |
| T-ENV-01 | lock / metadata / imports / paths | 固定候选、解释器与 entrypoints 一致 | REQ-002 |
| T-ENV-02 | clean env rebuild | 另一临时环境按锁重建，无 hardware access | REQ-002 |
| T-UI-01 | 真浏览器 no-device run | 无伪在线/自动连接；页面可用 | REQ-003/016 |
| T-UI-02 | GUI role/unit/fault inspection | 正确角色、单位、缺失/陈旧提示 | REQ-012/013/016 |
| T-OWN-01 | fixture 并发两个 start | 一个接受，另一个拒绝；资源释放 | REQ-011 |
| T-OWN-02 | fixture 跨模式/双tab/重试 | 无第二个硬件 owner；异常不自动重启 | REQ-011 |
| T-WEB-01 | 非可信 Origin/Host/WS，no-device | 写入/WS 不因宽 CORS 接受任意网页命令 | REQ-014 |
| T-STOP-01 | fixture start/cancel/failure | 状态准确，任务停止、资源释放，不假报 torque | REQ-011/016 |
| T-DEV-01 | OS枚举和人工差分识别 | 两端口各有角色，不使用 ACPI COM1 猜测 | REQ-004 |
| T-CAM-01 | 逐台映射/遮挡确认 | 不同实体设备绑定不同角色 | REQ-004 |
| T-CAM-02 | 双路60s有效采样 | 速率/无效帧/负载达到已声明目标 | REQ-004/012 |
| T-CAM-03 | 重插/换序后再次识别 | 不静默交换 wrist/front | REQ-004 |
| T-CAM-04 | preview→record 句柄交接 | 无抢占、黑屏或后台重复捕获 | REQ-011 |
| T-HW-01 | 现场 checklist + 受批准配置 | 电源/安装/角色/校准事实一致 | REQ-005 |
| T-HW-02 | 小范围主从/停止验证 | 方向合理、无意外首跳、停止后状态明确 | REQ-005 |
| T-DATA-01 | 官方 loader + metadata/media | 三真实回合，两路媒体和 schema 一致 | REQ-006 |
| T-DATA-02 | 逐回合首/末/越界帧 | frame/episode/media 对齐，不跨回合 | REQ-006/007 |
| T-DATA-03 | 禁串口/禁robot constructor的 browse | 本地查看无执行器访问、无需Hub | REQ-007 |
| T-DATA-04 | fixture 中断/缺帧/未finalize | 明确错误、原件保留、修复可追溯 | REQ-006/016 |
| T-DATA-05 | 固定record code与实际样本 | action来源、单位、顺序、reset含义明确 | REQ-012 |
| T-TRAIN-01 | 小batch/short smoke/checkpoint reload | 有限输出、配置齐全，资源预算正确 | REQ-008 |
| T-EVAL-01 | 有限现场N次 | 所有尝试进入报告，失败/中止不删 | REQ-009 |
| T-PRIV-01 | staged paths / logs / screenshots audit | 无原始数据、token、serial、家庭图片泄露 | REQ-014 |
| T-LINK-01 | 脱敏摘要与来源核对 | 父只读关联无控制入口、无私密paths | REQ-010 |
| T-PATCH-01 | fresh pinned checkout + apply + test | 补丁可重建/可撤销，不靠site-packages | REQ-015 |

## 3. 现有包测试与未来运行测试

本包实际提供 `tools/validate_pack.py` 和其 unittest：检查文档存在、JSON 解析、源 ID、链接、root规范、候选 SHA、示例角色、禁止误设 motion、manifest 完整性。
这些工具不安装 LeLab、不验证 dependency resolution、不连接设备，不证明以上全部运行矩阵已实现。
M1/M5 根据实际源码建立对应无设备 tests。当前本地候选为 54 项项目 Python 回归、268 项固定 LeLab 回归和 15 项前端 Vitest；其中真实编码的 synthetic MP4/Parquet fixture 验证 Dataset v3、finalize、loader、CPU DataLoader、同 ID resume 与三回合累计，但只证明软件路径，不输出“robot passed”或“三个真实回合”。

## 4. 必要负测试

错误端口；同一路相机绑定两角色；被其他程序占用的相机；清单中缺少calibration；损坏/共享MP4边界；空/NaN/Inf限幅；旧 session 控制新任务；延迟 worker release；Stop 后动作/reset；超时无界重录；跨模式并发；无效Origin；断开的WS；UI截图有静态零值但后台无设备。
动态异常先在 fixture 注入，不自动用拔插带电机械臂做 fault injection。
未测场景标 NOT_RUN，不把被禁用的按钮当后端保护已通过。

## 5. 性能采样

相机试验记录请求fps/实际有效到帧率/有效数量/错误数量/时间间隔分位数；raw sensor时钟无接口则 unavailable。
记录全流程CPU/RAM/可用磁盘，不能只测一个 camera单独打开。
策略测试记录预处理、推理和发出目标之前耗时，说明同步/异步语义。UI FPS不等于control Hz。
门槛是项目工程目标并随场景合理调整；变更要记录原因，不能为通过测试临时放宽不报告。

## 6. 证据文件与脱敏

真实日志/截图保存在 `.local/evidence/<run_id>/`，不进 Git。
允许提交摘要：版本、用例ID、结果、限制、经脱敏的必要输出；引用 local artifact ID，不泄露绝对目录和serial。
每次修复跑针对性回归；milestone候选跑该阶段全部用例一次。没有必要每改一行重跑所有未来硬件gate。

## 7. 判定

PASS：该具体用例真实运行并满足退出条件。
FAIL：运行且出现不符合。
BLOCKED：依赖/授权/设备不足，尚未运行相应操作。
NOT_RUN：未执行，不说明通过或失败。
对软件可继续部分单独 closeout；不因现场准入未到就把整个项目报告为失败或完成。
