# Computer Use / Browser Debugging Protocol

## 1. 工具不是默认存在，也不是控制授权

在实际Codex会话检查本地Browser、Computer Use、终端和MCP的能力、权限及目标主机。
官方文档说明支持地区中的Windows/macOS可使用Computer Use；具体账户/环境仍以实际可用性为准。不要依据旧新闻断言英国永远不可用，也不要保证当前一定可用。
本地Web应用优先Browser自动化；原生设备管理器或视觉问题用Computer Use。
如果某工具不可用，记录事实，用可用的CLI/API进行相应验证，未做的视觉用例标NOT_RUN；不谎称截图验证。

## 2. 前台与隐私

Windows Computer Use使用活动桌面；目标窗口必须可见。不要同时抢用户鼠标键盘。
关闭无关敏感应用，限制截图到本工作台；token/密码/个人邮件/公司材料不进入诊断截图。
截图作为模型输入可能离开设备，这是与不上传训练数据不同的边界。只采集任务必要视图。
不操作ChatGPT或终端GUI绕过安全规则；使用正式shell工具运行命令，不代替用户批准UAC/系统权限。

## 3. 按风险验证，不能“所有按钮都点一遍”

软件路径：首页、版本、设置查看、空设备/错误页、local dataset browser。
观察路径：已确认两相机preview，保存有限诊断截图。
配置/动作路径：Calibrate、Teleoperate、Record、Replay、Inference，只在对应C/D现场权限成立后。
外部/破坏路径：Upload、Cloud train、Delete、Update、driver/firmware install，独立确认。

## 4. 每个缺陷的复现闭环

记录：真实版本/页面 → 初始状态 → 最少步骤 → 预期/实际 → 控制台/后端日志/数据证据 → 最小原因假设 → 修改 → 同一路径重测。
截图不能替代后台结果；HTTP200不能替代用户看到的画面；浏览器toast不能证明回合finalize。
无需为每次点击截屏；关键状态转换、错误、修复前后各有必要证据即可。

## 5. 必查视觉用例

空状态无假在线；错误端口不会跳到“完成”；相机角色不互换；两画面可区分；单位正确；数据陈旧不是0度；录制与reset明确；保存数量真实；Browse与Replay明显不同；停止入口可见；不默认上传。
更改宽度后重要动作不被遮挡；颜色之外有文字状态。只改相关组件，不把bugfix扩成全面redesign。

## 6. 多窗口与重试

一个场景一次操作。检查弹窗/焦点/前后端是否同一进程/同一版本。
重复点击、双tab和网络重试用fixture验证。涉及movement的timeout后先确认实际状态，不自动再点击。
运动中人必须能独立停止；Codex不应占用人唯一的急停交互路径。

## 7. 结束

关闭预览/测试任务、确认资源owner释放、保存本地证据；关闭浏览器不等于关掉后台。
报告实际工具、已执行用例、未执行项目和剩余风险。不说“全部正常”而不限定范围。

Official source: [Computer Use](https://developers.openai.com/codex/app/computer-use/)。
