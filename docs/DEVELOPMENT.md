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
