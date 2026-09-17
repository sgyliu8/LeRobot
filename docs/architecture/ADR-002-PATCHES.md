# ADR-002 — 不造轮子不等于禁止修上游缺口

**Status:** accepted planning baseline. **Scope:** minimum necessary LeLab integration fixes.

## Decision hierarchy

已有功能 → 已支持配置 → 同版本官方 CLI → 最小可重建补丁 → 证据充分的新模块。
不把任何软件故障直接归因于“框架不好”，也不因 upstream branding 跳过验证。

## Candidate issues from source review

1. launcher 的停止发现逻辑可按 8000/8080 监听端口加入 PID；端口属于别的应用时不应由本项目停止。先不用盲目 `lelab --stop`，用已知 own-process lifecycle；必要时修限定。
2. telemetry helper 对全部 `.pos` 执行角度转换并可对错误返回零；夹爪的归一化值及未知读数不得作为精确 joint angle/当前零位。显示语义必须处理，但不必重写3D renderer。
3. teleoperate/record 创建 follower config 的片段没有传递项目限定的 max_relative_target；默认 None。首动限制不能只写在本项目 JSON 而未进入实际配置。
4. 各模块自己的锁和跨模块 active flag 检查不等于已证明全局原子互斥；用无设备并发测试确定是否需共享锁。
5. server 中宽 CORS 不应被当作硬件写入安全边界；针对实际 write/WS 接口验证并局部加固。

以上是静态检查定位的风险/缺口，不声称所有故障已在本机复现。未复现且无当前需求的项目不扩写。

## Implementation contract

只在确认问题影响当前验收后，把 upstream 固定到 `_vendor/lelab`，checkout exact commit。
tracked `patches/` 仅在第一份实际 patch 产生时创建；每 patch 配一段原因、upstream commit、涉及文件、测试和回滚。
用标准 git diff/apply；不把整个 vendor 源码提交；不编辑已安装 site-packages。
安装入口与锁定必须明确指向 patched checkout，展示 import file path，避免“修了源码但运行旧包”。
每个 patch 先 no-device regression，之后重跑受影响 GUI 和必要台架 gate。
若 upstream 解决同一问题，做替换对照后移除 patch；不要无限维护叉版本。

## Non-goals

不建立插件市场、通用机器人安全OS、全套新状态服务器、云控制面或新的 dataset 格式。
不把软件限制命名为经过认证的安全控制器，不增加“看似完备但未测试”的急停按钮。
