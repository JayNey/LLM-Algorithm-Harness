---
change: benchmark-run-history
design-doc: openspec/changes/benchmark-run-history/design.md
base-ref: d888e0390c0d49d9119a30a7aa068fd963affeae
archived-with: 2026-11-01-benchmark-run-history
---

# 实施计划

<!-- comet-task-authority: openspec/changes/benchmark-run-history/tasks.md -->

采用用户确认的 autonomous / tdd / standard。范围及技术取舍以已确认 design.md 和 delta spec 为准。保持独立分支；修复在该范围内的问题，无需重复确认；不自动合并 PR。

按以下依赖顺序实施。每项先写能复现待实现行为的测试，记录真实 RED，再写最小实现并记录 GREEN；环境错误不记为行为 RED。任务状态只更新 tasks.md。受风险影响的分段和最终集成由独立审查者核对。

## 1.1

<!-- comet-task-ref:e603f607-7f82-4817-9788-63cb2f4a2e4c -->

1.1 扩展历史分页、任务关联和曲线标识的前端类型/严格解析；通过客户端契约测试验证真实分页参数、空页、可空 task_id、run_id 和非法响应。

## 1.2

<!-- comet-task-ref:148b7e48-34e7-41f9-bb25-f4c5077e8e59 -->

1.2 实现 URL 查询和运行选择策略；以测试验证刷新恢复、保留其他参数、分页外显式运行、无效 URL 及活动运行唯一/多条选择。

## 2.1

<!-- comet-task-ref:3942f49e-6368-464e-b87e-61329e1b4e45 -->

2.1 接入真实历史表、状态筛选/分页、活动运行入口和选中详情；页面回归覆盖空态、403/404、跨套件关联拒绝及原模型/数据集表单保留。

## 2.2

<!-- comet-task-ref:7d69df2b-10fe-4e86-8d1a-c8a54d5c3891 -->

2.2 实现选中运行关联任务的进度观察、暂停手动刷新、终态资源对账及提交锁；验证终态停止、失败重试、路由/账号变化清理和旧响应隔离。

## 2.3

<!-- comet-task-ref:e32654b0-18a8-41ef-b4ce-b3f6ab44e0df -->

2.3 接入曲线 run_id 导航和键盘等价链接，补齐双语与窄屏样式；通过曲线选择、键盘和 320px 布局检查。

## 3.1

<!-- comet-task-ref:bb6f51be-9e14-4382-a7e3-379c1396eb96 -->

3.1 完成真实 HTTP 与浏览器联调、前端测试/lint/类型构建和相邻表单回归；交付可复跑脚本及标明播种/替身边界的验证报告。

## 3.2

<!-- comet-task-ref:e64054f8-2807-48fd-9e7a-04a51c52acf6 -->

3.2 完成分段独立审查并修复问题，核对规格和提交归属，备齐独立 PR 交付材料；以实际复审、检查及提交记录验收。

## 实施边界与回退

以现有 HTTP 客户端、所有者与实体关联为信任边界；不得从 UI 标识猜测任务。先验证合同和纯状态策略，再接观察/发布与界面/路由，最后跑跨模块联调。失败先定位根因并补回归；保留通过检查对应的提交引用和故障证据。

前端合同 → URL/关联策略 → 历史及详情 → 进度生命周期 → 曲线与双语布局 → HTTP/浏览器验收。复用真实历史接口、会话 provider 和 AbortSignal，不修改 B3；明确选择的 run 直接加载。终态刷新采用去重签名，提交采用同步锁。前端回退可直接撤回代码，不影响运行数据。

检查：node --experimental-strip-types --test src/benchmarks/*.test.ts、npm test、npm run lint、npm run build；浏览器覆盖 320px、语言、刷新/分享、多活动运行、分页外记录、错误、账号和路由切换。HTTP 联调用隔离真实 API，数据播种边界必须写清。
