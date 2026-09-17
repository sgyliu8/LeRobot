# Git, CI and Release Policy

## 1. 当前约束

目标远端公开且当前无 branches，需在执行时复核。父项目历史上暂停 hosted CI 的原因不能当作本月额度事实。
本项目默认 **local-first validation、无自动 hosted workflow**。本包不附 `.github/workflows`，避免首推就烧算力或执行未审操作。
需要远端 CI 时再建最小静态检查 workflow；不允许 self-hosted runner 自动连接机械臂。

## 2. 空仓库启动

M0 确认 empty remote 后，建立只含受控 pack的 initial main 文档基线，检查暂存文件后首次 push。
然后创建 `codex/bootstrap-so101-lab` 做环境/软件；普通提交和该 feature branch push 可继续。
如果 remote已有历史，在保留已有文件和历史的情况下适配；不使用 force、reset --hard、删除目录或无条件覆盖来“恢复空仓库”。
父 repo 不 commit、不改 remote、不merge、不clean。子 repo里的Git命令每次检查根和remote。

## 3. 分级检查

文档/示例：pack validator + 改动语义检查。
源代码patch：相关unit/contract tests + import + 指定fixture。
UI：只跑受影响flow的browser/Computer Use及必要backend检查。
采集/硬件：现场范围内的对应gate，不进入普通自动CI。
milestone候选：该阶段综合gate + staged privacy审计 + accurate HANDOFF/CHANGELOG。
首次依赖基线做一次clean-env重建，不每个MD修改重新安装。

## 4. 文件与提交

使用有意义、可回滚的commit；不要求任意固定行数或“所有小改都5人review”。
源码、测试、文档和对应patch一起提交；原始数据、日志、截图、model不提交。
公开push前至少看 `git diff --cached --stat`、`git diff --cached --name-only` 与必要内容；大文件或私密path停下纠正。
本包 .gitignore 不是数据防泄漏的完整保证；已tracked文件不会因为加ignore自动消失。

## 5. PR与发布

有实质实现后可以创建Draft PR，正文写实际版本/验证/NOT_RUN和剩余风险。
不自动merge、release、tag、公开托管实验门户或发布dataset。发布是另一决定。
review角色可以由Codex可用的独立agent承担，但必须记录实际agent数/执行模式，不能把单agent五视角说成五位独立专家。
合并前P0/P1式结论应明确针对软件范围，不自动覆盖机械安全。

## 6. 校验与哈希

Git commit + lockfile + exact upstream revision足以支持大多数代码追溯。
不对每次Markdown更新计算sha256，不做周期性全盘扫描。
模型检查点、正式数据快照或最终发布archive需要身份时计算一次并记录；不以哈希数量替代可运行性。

## 7. 结束报告

起始/最终root、branch、HEAD、worktree、upstream；新增/变更的依赖与patch；实际命令和PASS/FAIL/BLOCKED/NOT_RUN；UI/数据证据；原始数据去向；必要parent local exclude例外；下一ready milestone。
一个提交不能包含它自己的最终hash；终端回执/PR评论绑定最终hash，不反复追加自引用commit。
