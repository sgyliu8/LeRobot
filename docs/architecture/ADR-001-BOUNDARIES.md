# ADR-001 — 子仓库、现有 UI 与研究平台的边界

**Status:** accepted planning baseline when the owner submits the startup prompt. **Date:** 2026-09-17.

## Context

用户已选 `Physical_AI\Lerobot` 作为新目录，`sgyliu8/LeRobot` 作为独立 remote；父平台已经拥有成熟研究文档、Astro 页面与自己的开发历史。
LeLab 提供目标工作流，LeRobot 提供设备/数据/学习能力。重写外壳既增加维护量，也可能引入第二个设备访问者。

## Decision

本目录独立 Git；父 repo local info/exclude 排除它，不建立 submodule。
保留 LeLab 的本地 UI/backend，不把父 Astro 项目改为控制服务器。
子 repo 维护锁定配置、启动/诊断、质量门槛、实验 sidecars 和必要源码 patches；上游依赖不复制为用户原创项目。
Python distribution/namespace 与官方 lerobot 名称分离。
第一阶段 Windows 原生，不把 WSL/容器/ROS 2 作为前置条件。

## Alternatives considered

父 monorepo：能共用导航，但混淆现有权限/环境/CI和用户指定 remote，拒绝。
从零自建 React/PySide：能自由布局，但重复上游工作和设备状态机，拒绝。
正式 fork 整个 LeRobot：只有需要长期改变学习框架时才考虑，首版不采用。
ROS 2 先行：适合多模块调度，但不是当前模仿学习链路所需，延期。

## Consequences

有两个独立启动入口，但一套明确设备 owner；初期统一体验靠链接而不是跨服务控制。
父仓库不能版本控制子内容；公开网页无法自动访问本地机械臂。
缓存可能仍由 upstream 放在 home，需要 scoped identity/backup，而非误以为虚拟环境隔离一切。

## Acceptance / reversal

M0验证root/remote/ignore，M1验证runtime separation，M8验证摘要不泄露路径。
只有真实跨应用操作需要且有测试/权限设计时才重议；不因“统一平台看起来更完整”推翻。
