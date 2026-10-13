# Development

本项目以固定上游和最小 patch 为基础。修改应优先留在项目脚本、测试或单个可重建 patch 中，
不能直接编辑 site-packages，也不应复制 LeLab/LeRobot 框架。

## 固定运行栈

| 组件 | 固定身份 |
|---|---|
| Python | 3.12，当前解析为 3.12.13 |
| uv | 锁文件由 0.12.4 生成 |
| LeLab | `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` |
| LeRobot | v0.6.0 / `30da8e687a6dfc617fcd94afc367ac7071c376ce` |
| MuJoCo Menagerie SO101 | `8161bba264d7fa7c99ca301e91e7fb44737676ad` |

机器可读身份以 [`configs/upstream-pins.json`](../configs/upstream-pins.json) 和 `uv.lock` 为准。

## 修改流程

1. 确认 Git 根、分支、remote 和干净/已知 worktree。
2. 先用无硬件 fixture 复现问题；测试必须拦截真实设备构造。
3. 在 `_vendor/lelab` 的固定 checkout 上做最小修复。
4. 用下面的 full-index/binary 流程更新唯一 patch；不要提交 vendor checkout。
5. 运行最小相关测试，再运行项目回归和 fresh-apply/build gate。
6. 只提交脱敏代码、配置示例和合成测试资产。

## 验证命令

```powershell
# 锁文件和导入来源
uv lock --check
uv run --frozen python -X utf8 -c "import lelab, lerobot; print(lelab.__file__); print(lerobot.__file__)"

# 公共文档和配置示例
uv run --frozen python -X utf8 .\tools\validate_docs.py

# 项目无硬件回归
uv run --frozen --group test python -X utf8 -m pytest -q tests

# 固定上游测试
uv run --frozen --group test python -X utf8 -m pytest -q _vendor\lelab\tests

# 前端
Set-Location .\_vendor\lelab\frontend
npm test
npm run typecheck
npm run lint
npm run build
npm audit
```

测试通过只证明对应 fixture 与软件合同。除非测试显式拦截设备构造，否则不能称为无硬件测试；
任何 mock、HTTP 200 或绿色 UI 都不能计作真机验证。

## Fresh patch 验证

先从固定 vendor checkout 重建包含新增、删除和二进制前端产物的 patch：

```powershell
git -C .\_vendor\lelab add -A
git -C .\_vendor\lelab diff --cached --binary --full-index HEAD `
  --output ..\..\patches\lelab-6091a458-so101-lab.patch
git -C .\_vendor\lelab reset
```

确认 patch 同时包含新增 worker、后端测试和打包前端；不要用只比较已跟踪文件的命令遗漏新增文件。

在临时目录或可安全重建的干净 vendor checkout 中：

```powershell
git apply --check ..\..\patches\lelab-6091a458-so101-lab.patch
git apply ..\..\patches\lelab-6091a458-so101-lab.patch
git apply --reverse --check ..\..\patches\lelab-6091a458-so101-lab.patch
```

随后运行后端测试、前端测试和 build。不要在含未保存修改的 vendor checkout 上机械覆盖。
fresh checkout 的实际导入路径也必须指向该临时 checkout；当前开发 checkout 测试通过不能替代
fresh-apply 验收。

用户安装/更新统一使用 `Start-SO101-Lab.cmd setup/update`。维护中不要绕过互斥入口另行启动服务。
可用 `tools/bootstrap_upstream.ps1 -CheckOnly` 只核对固定 patch；
`-Rebuild` 在旁边构建新 vendor 并保留旧目录。开发期间修改源码后，应先生成 patch，
再 Setup 记录安装身份，不能直接伪造安装凭据。

## 前端依赖维护

前端依赖锁随同一个上游 patch 保存，必须在 `_vendor/lelab/frontend` 中运行 `npm ci` 和在线
`npm audit`；离线安装提示不能替代在线审计，不使用 `npm audit fix --force` 或忽略规则隐藏告警。
当前构建使用 Tailwind CSS / PostCSS 插件 `4.3.3`、tailwind-merge `3.7.0` 和 source-map-js `1.2.2`。
无官方修复版的 braces 依赖链已从构建中移除，同时移除引入旧链的开发标记工具和未启用的 typography 插件。
既有界面沿用原主题配置；焦点、阴影、收缩和弹窗变量写法按
[Tailwind 升级说明](https://tailwindcss.com/docs/upgrade-guide)适配，并有实际 CSS 编译回归。
浏览器使用当前 Edge / Chrome；Tailwind 4 的最低要求为 Chrome 111、Safari 16.4 或 Firefox 128。

更新依赖后运行前端测试、lint、build、在线 audit 和 fresh patch 重建，并在实际浏览器检查表单与弹窗。
低内存开发电脑可使用 `npm test -- --maxWorkers=1`。这些检查不启动训练、相机或机器人。
Recharts 固定为 `3.10.1`，`react-is` 与 React 同为 `18.3.1`，按
[官方迁移说明](https://github.com/recharts/recharts/wiki/3.0-migration-guide)验证。
动作曲线通过公开坐标接口解析点击帧，命中层位于曲线之上；保留悬停提示，并在切换回合时清除旧曲线。
回归使用真实 Recharts 渲染，覆盖首/中/末帧、无悬停点击、旧悬停位置、越界、回合切换和训练指标更新。
未被产品代码使用的 `@react-three/drei` / `@react-three/fiber` 已移除，连带移除弃用的 BVH 依赖；
机器人视图仍使用 Three.js `0.177.0` 和 URDF Loader `0.12.7`，类型声明与 Three.js 版本对齐。
模型回归解析随软件附带的 SO101 URDF、全部视觉 STL 和关节变换；浏览器检查实际模型显示。
上游弃用提示与漏洞报告分开记录，不通过忽略规则或强制覆盖 peer dependency 隐藏问题。

完整类型检查运行 `npm run typecheck`，同时检查应用（包括测试）和 Vite 构建配置。
`npm run build` 与 `npm run build:dev` 都先运行此门禁，类型错误会阻止打包；不能用 Vite
打包成功代替类型检查。既有 12 项应用诊断及一项构建配置诊断已修复，未关闭空值检查、排除测试
或加入类型抑制。相机缺少 FPS 时仍拒绝录制，不自动补一个值改变已冻结的配置。

按 [Vite 8 迁移说明](https://vite.dev/guide/migration.html)和已安装版本的类型接口，
生产日志精简改用 `build.rolldownOptions.treeshake.manualPureFunctions`，不再使用失效的
`esbuild.pure`。内存构建回归验证普通日志被移除、警告/错误保留、日志参数中的副作用仍执行；
development 模式仍保留日志。此修复没有更新任何依赖版本或锁文件。

## 热更新、按需加载与服务生命周期

组件/Provider 文件只导出组件；共用 Context、Hook 和样式函数放在独立模块，避免热更新失去状态。
`npm run lint` 使用 `--max-warnings=0`，没有关闭 Fast Refresh 规则。开发浏览器验证还会在引导途中
编辑 Provider，检查进度保留、欢迎弹窗不重复出现；临时探针不随补丁发布。

首页保持直接加载，其他页面使用 React lazy/Suspense；3D 引擎保留 Three 官方 core/renderer 边界。
加载失败会明确提示，不自动刷新页面或重发任务；全局停止提示位于页面加载边界之外。
[Rolldown 分包](https://rolldown.rs/reference/OutputOptions.codeSplitting)配置不调高 Vite 的 500 kB
告警阈值。真实应用内存构建测试检查每个 JS 块小于 500 kB、首页静态依赖总和小于 550 kB，并确认
Three/Recharts 没有进入首页依赖。这里测的是压缩前的构建 JS 字节，不是网络速度或整站总体积。

FastAPI 使用[官方 lifespan 接口](https://fastapi.tiangolo.com/advanced/events/)，保持一次启动诊断，
正常退出、服务异常和启动失败均停止广播，不借启动访问设备。Starlette 固定 `1.7.0`，采用其
[AnyIO 4.15 兼容修复](https://starlette.dev/release-notes/#170-september-23-2026)；FastAPI、AnyIO、
LeLab/LeRobot 与训练依赖不升级。测试组固定 `httpx2==2.13.1`，仅替换 TestClient 的弃用后端选择，
生产 HTTPX 依赖仍保留。`uv sync --frozen --group test` 可安装同一已验证组合。
回归执行 `python -m pytest -q -W error::DeprecationWarning tests _vendor/lelab/tests`，不屏蔽弃用提示。
Vite 仍可能给出 SWC 插件替换建议或构建耗时提示；它们不属于上述三类告警，也没有被过滤。

## 测试数据规则

- MP4/Parquet fixture 必须明确标记 synthetic。
- fixture 写入临时目录，不能指向用户真实数据根。
- destructive/repair 路径必须证明不会修改原始数据。
- 硬件测试默认 `NOT_RUN`，除非记录了当次设备、现场条件与实际证据。
- Dataset loader、视频 EOF、resume 和时间语义应分别测试，不能用一个“可打开”断言替代。

## 文档规则

GitHub 文档保持用户导向，只描述当前产品、操作和已验证状态：

- 不提交本机绝对路径、设备 ID、校准内容、原始日志或账户信息；
- 不把内部交接、提示词、审查过程或逐版本流水账作为用户入口；
- 当前状态只在 [Project Status](PROJECT_STATUS.md) 维护；
- README 保持短路径导航，深入说明放在对应主题页。
