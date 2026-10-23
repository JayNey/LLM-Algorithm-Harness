# Design: benchmarks-abtests

> 范围：#166 第②步。范围对齐声明见 issue #166 留言（2026-10-23）。基线 5810e9f6（含第①步实验簇）。

## 契约盘点（upstream/main 5810e9f6，已核对）

- **Suite 视图** `_suite_view`：`{id, name, version, description|null, frozen, problems[], created_at, updated_at}`；创建/编辑 schema：`name(min1,max200)`、`problems(min1)`、`version(默认"1.0",max32)`、`description?`、`frozen(默认false)`；PATCH 同字段全可选。`GET /benchmarks/suites` **无分页参数**（全量返回，PaginatedData 壳 limit=总数）。
- **Run 视图** `_run_view`：`{id, suite_id, status, model, accuracy|null, cost_usd|null, error_message|null, created_at, updated_at}`（include_results 时附 `results`——本 change 不解析明细）。`POST .../run`（202 + task_id，Celery，进度在 `GET /tasks/{id}`，与实验同构）；**无 run 列表端点**；`GET /benchmarks/runs/{run_id}` 单查。
- **学习曲线** `GET /benchmarks/learning-curve/{suite_id}`：`{suite_id, suite_name, data:[{timestamp, model, accuracy, cost_usd}]（仅 completed，按时间排序）, trends:{accuracy_growth_rate, cost_growth_rate}（<2 条为 null）}`。
- **AB 视图** `_job_view`：与实验同构 7 字段（id/name/status/config/error_message/created_at/updated_at）；`config` = ABTestCreateRequest JSON（`name/dataset_path/model(ModelSpec)/strategy(StrategyConfig)/prompt_variants(恰2)/baseline_id?/seed(默认42)/max_workers(1..20)/api_key_id`）。启动 202 **无 task_id**（进程内 daemon 线程，重启标 failed）→ 只能轮询 `GET /ab-tests/{id}` 状态。结果 `GET /ab-tests/{id}/results` = ab_test.json：前端消费子集 `variants[2]{id,description}`、`comparison.sample|formal`（`baseline/treatment: rate|null` + `ci95{difference,lower,upper: number|null}`）、`comparison.statistics{categorical_test∈fisher_exact|chi_square|unavailable, p_value|null, welch_t_p_value|null}`、`comparison.elapsed_seconds/tokens/failure_categories`。
- **前端现状**：/benchmarks 路由挂 mock；/ab-tests 无路由；第①步的 `useTaskProgress`/`useList`/charts/严格解析器风格可复用。

## 关键决策

1. **两个自包含簇**：`frontend/src/benchmarks/`（types/client/session/validation/presentation）与 `frontend/src/abtests/`（types/validation/client/session/presentation）。AB 创建为页面内联受控状态（创建即导航，无独立启动相位），未引入 runCreation store。严格解析只解析 UI 消费字段；`results` 明细不解析（设计明确声明）。
2. **进度通道**：基准 run 复用 `@/experiments/useTaskProgress`（跨簇复用已由 useList 先例）；AB 启动无 task_id → 详情页以 5s 间隔轮询 `GET /ab-tests/{id}` 状态至终态（同类快照派生模式，内联实现）。
3. **页面形态**：BenchmarksPage 顶部内联「创建 Suite」折叠面板（字段少，不值得独立路由）+ 套件卡片列表（名称/版本/题目数/冻结态/编辑按钮）；BenchmarkDetailPage = 套件信息 + 编辑（PATCH）+ 启动 run 表单 + run 进度（task_id 锚定）+ 学习曲线 Tab（TrendLine 折线 + trends 数字）。ABTestsPage 同实验列表模式（useList 分页 + 状态筛选）；CreateABTestPage 动态双变体表单；ABTestDetailPage 状态轮询 + 完成后统计表（含 ci95 区间与检验方法三态）。
4. **图表**：`TrendLine` 加入 CompareCharts.tsx——按 model 分组的准确率折线（y=accuracy）+ 可切换成本折线（y=cost_usd），trends 以文字呈现。
5. **测试**：benchmarks client.test（suite/run/learning-curve 解析、无分页壳容忍）、abtests client.test（job/config/results 子集、statistics 三态含全 null）、abtests validation.test（双变体必填、max_workers 1–20、seed 非负）；package.json glob 追加。
6. **verify 脚本**：`scripts/verify-benchmarks.mjs`（suite 列表+创建+学习曲线场景、ab 列表+详情场景，浏览器 fixture 层），QA.md 追加说明，不进 CI。

## 风险与回退

- routes/AppLayout 增量追加（与并行批次冲突面同第①步，追加式合并）。
- AB 结果报告形状以源码为准做了子集冻结，任何漂移显式报错。
- 回退：删两个新簇目录 + 还原三处增量。
