# Proposal: experiments-frontend（issue #166 第①步：实验管理前端簇）

## Why

issue #166 要求实验管理、基准测试与 A/B 测试的前端界面。后端契约已全部就绪（experiments/benchmarks/ab_tests/optimize/pareto 路由于 #156 批次合入），前端对应页面仍是 Mock 占位。本 change 交付第①步——**实验管理簇**（创建 / 列表 / 详情 + 对比报告 + 胜率矩阵 + 帕累托 + 成本建议）；基准 Suite 与 AB 测试簇按 issue 留言声明的两步交付计划，随后续 change 实施。范围已按 main 真实契约对齐（issue 正文为 2026-10-10 设想，多处字段/端点与现状不符），并在 issue #166 留言向维护者声明。

## What Changes

- 新增 `frontend/src/experiments/` 功能簇（evaluations 同构模式）：`types.ts`（严格类型）、`validation.ts`（查询与草稿白名单校验）、`client.ts`（严格解析：list/get/create/remove/run/results/comparison/panel + 通用任务 `task(taskId)`/`cancelTask(taskId)`/`runningTasksIndex` + 无状态分析 `pareto/optimize`）、`session.tsx`（marker 键控 SessionProvider）、`runCreation.ts`（创建→启动状态机，operation 计数防竞态）、`presentation.ts`（状态/指标中文标签）。
- 新增进度轮询：`useTaskProgress(taskId)`（3s 轮询 `GET /tasks/{task_id}` 至终态；experiment/benchmark 无 WS，契约依据 api/routes/ws.py 仅支持 evaluation）。
- 新增三个页面替换 Mock 占位：`pages/Experiments/ExperimentsPage.tsx`（服务端分页列表 + 状态筛选 + 删除 + 运行中取消经任务通道）、`CreateExperimentPage.tsx`（名称/数据集/多模型/多策略/预算三型/重复次数/serial|parallel/max_workers/API Key）、`ExperimentDetailPage.tsx`（概览+进度轮询、对比报告、胜率矩阵热力图 + McNemar 显著性、panel 雷达/散点/柱状、帕累托前沿、成本优化建议）。
- 图表用已在依赖中的 echarts/echarts-for-react（热力图/散点/雷达/柱状），零新增依赖。
- `routes.tsx` 增量添加 `/experiments/new`、`/experiments/:experimentId`；`package.json` test glob 追加 `src/experiments`。
- 单测：client/validation/runCreation/presentation（node:test + strip-types，注入假 http 与假时钟）。
- 新增 `frontend/scripts/verify-experiments.mjs`（create/list/detail 场景，浏览器 fixture 层，骨架同 verify-evaluations.mjs）。

**明确不做（后端当前不支持，前端不模拟，已在 issue 留言声明为后端依赖）**：克隆配置、实验关键词搜索、Suite 删除、Benchmark run 列表、AB 取消、预估完成时间、里程碑/σ/版本差异、分层 AB、报告导出端点、数据集选择器、`cost_usd` 预算、`parallel_granularity`。**基准与 AB 页面属第②步后续 change**。

## Capabilities

### New Capabilities

- `frontend/experiments-management`：实验创建/列表/详情/对比分析的前端能力（含进度轮询、取消经任务通道、胜率矩阵与显著性、帕累托与成本建议展示）。

### Modified Capabilities

- 无：不改既有 evaluations 簇与任何后端行为；routes.tsx 与 package.json 为增量修改。

## Impact

- 新文件约 13 个，修改 2 个（routes.tsx、package.json），均自包含于前端。
- 不新增 npm 依赖；不触碰 evaluations/benchmarks/abtests 现有代码；verify 脚本不进 CI（与既有 QA 流程一致，手动运行）。
- 真实评估批次正在并行修改 routes.tsx 的 detailPages——本 change 只追加 experiments 条目，冲突面为追加式合并。
