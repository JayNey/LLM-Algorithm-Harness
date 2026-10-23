# Proposal: benchmarks-abtests（issue #166 第②步：基准 Suite + 学习曲线 + AB 测试页）

## Why

第①步（PR #246，已合并）交付了实验管理簇与可复用的图表/任务轮询基建。本 change 交付第②步：基准 Suite 管理（含学习曲线）与 A/B 测试页，补齐 #166 剩余的前端面。范围已在 issue #166 留言（2026-10-23）与维护者对齐，后端不支持的子项继续不做假入口。

## What Changes

- 新增 `frontend/src/benchmarks/`：严格解析 client（suites 列表/创建/详情/编辑/run/run 详情/learning-curve + 任务进度通道复用 experiments 的 `useTaskProgress`）、session、presentation；页面：`/benchmarks` 列表（含内联创建与编辑）、`/benchmarks/:suiteId` 详情（套件信息 + 学习曲线折线图 + 启动 run + run 进度与结果标量）。
- 新增 `frontend/src/abtests/`：严格解析 client（list/get/create/remove/run/results）、session、创建相位机、presentation；页面：`/ab-tests` 列表、`/ab-tests/new` 创建（单模型单策略 + 恰好两个 prompt 变体）、`/ab-tests/:testId` 详情（状态轮询 + 完成后统计展示：sample/formal 的 baseline·treatment·ci95、categorical_test 三态 p 值 + Welch t、失败分类）。
- 图表：`components/charts/CompareCharts.tsx` 追加 `TrendLine`（学习曲线：多模型准确率与成本折线 + trends 增长率）。
- `routes.tsx` 增量：`/benchmarks/:suiteId`、`/ab-tests`、`/ab-tests/new`、`/ab-tests/:testId`（`/benchmarks` 由 mock 换真实页）；AppLayout 增挂两个 SessionProvider。
- `package.json` test glob 追加 `src/benchmarks`、`src/abtests`；新增 `scripts/verify-benchmarks.mjs`（suite 列表/创建/学习曲线/AB 详情场景，浏览器 fixture 层）+ QA.md 说明。

**明确不做（后端不支持，issue 留言已声明）**：Suite 删除、Benchmark run 列表端点（历史经学习曲线呈现）、AB 取消（进程内线程无 task 通道）、分层 AB、σ/标准差/版本间差异/里程碑、数据集选择器。run 的 `results` 明细子结构不在本 change 解析（详情页展示标量字段，历史趋势走学习曲线）。

## Capabilities

### New Capabilities

- `frontend/benchmark-management`：基准 Suite 的创建/编辑/启动/学习曲线观察能力。
- `frontend/abtest-management`：A/B 测试创建/列表/结果统计展示能力。

### Modified Capabilities

- 无：不改实验簇与任何后端行为；routes/AppLayout/package.json 为增量修改。

## Impact

- 新文件约 14 个，修改 3 个（routes.tsx、AppLayout.tsx、package.json）+ CompareCharts 追加。
- 复用第①步基建：`useTaskProgress`（基准 run 进度）、`useList`（AB 分页列表）、图表封装、严格解析器风格；不新增依赖。
- 与真实评估批次无共享文件冲突（新目录 + 增量路由）。
