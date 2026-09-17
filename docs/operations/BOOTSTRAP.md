# Bootstrap Runbook — M0/M1

## 1. 建立事实，不直接 git init 到错误位置

工作目录必须为 `C:\Project\Physical_AI\Lerobot`。
先查看已存在文件，保留用户改动和下载的 pack；本包初始状态不保证一直成立。

```powershell
$root = 'C:\Project\Physical_AI\Lerobot'
$parent = 'C:\Project\Physical_AI'
Test-Path -LiteralPath (Join-Path $root '.git')
git -C $root rev-parse --show-toplevel
git -C $parent status --short --branch
git -C $parent ls-files -- Lerobot
git -C $parent check-ignore -v -- Lerobot
git ls-remote --heads https://github.com/sgyliu8/LeRobot.git
```

第一次 `rev-parse` 可能显示父root，这恰恰是不能继续Git写入的信号。
如果父已跟踪本目录，不自动 rm --cached 或迁移；报告具体路径供一次性决策。

## 2. 本地排除与独立初始提交

确认父无 tracked child后，使用Git解析其info/exclude路径，保留原内容，幂等追加 `/Lerobot/`；复测check-ignore。只有这项parent metadata写入被本计划允许。
若remote空、target无自己的git，则在target执行 `git init -b main`，配置唯一origin为用户repo。
提交前运行pack validator和暂存隐私审计。初次main只包含文档、示例、schema、validator及必要repo配置；首次push不覆盖已有历史。
随后创建 `codex/bootstrap-so101-lab` 实施。
若remote非空，先查看实际历史并合并可兼容的pack；冲突时保留本地文件，禁止force/重置/删除后克隆。不要把先前“empty”陈述当授权覆盖。

## 3. 环境安装

读 DEPENDENCIES，检查磁盘、Python/uv/Git版本与项目root。
在child创建project pyproject与真实uv.lock；固定LeLab candidate，核对LeRobot resolved commit；独立`.venv`。
不在父`.venv`安装，不全局pip，不为了安装而关闭系统安全机制。
初次采用打包UI；只有构建实际改动才读前端package/lock/Node要求。

## 4. UI首次启动前

先源码确认import/startup不会自动连接机器人；核对进入主页是否自动打开相机。
记录本项目进程可执行路径、PID、创建时间和cwd；验证8000端口归属。
已有其他服务占用则报告并选择已支持的替代端口或等待用户处理，不杀进程。
不调用带电机的health-check。no-device测试通过dependency injection/fixture，不把已插USB当可任意连接。

## 5. GUI验证

打开真实local URL，验证首页、无设备状态、配置查看、错误路径和退出/重开。
查看浏览器console与backend日志，记录软件版本。必要时用Computer Use观察，不只是HTTP200。
锁定状态不点击Update，不登录Hub，不cloud train，不进入Calibrate/Replay/Inference。
如upstream缺失关键局部约束，按ADR-002做最小修复。

## 6. 起动脚本范围

Codex可以在M1实现一个可靠入口（例如START_LAB.cmd+PowerShell lifecycle），但本包不提供未经测试的伪installer。
脚本从自身路径定位repo/venv，不假定用户cwd；状态命令不打开设备；stop只控制已确认owner进程。
首次安装与日常启动分开：日常启动不能自动upgrade、重新校准或下载大模型。
关闭失败先确认是否仍有硬件owner；不能为“确保关闭”直接kill全端口进程树。

## 7. 交接

记录依赖锁、实际路径、已完成测试、截图/日志本地位置、端口和设备未确认项。
M1通过后继续M2/M3，不因为还没有GPU或hand-eye而停止。
