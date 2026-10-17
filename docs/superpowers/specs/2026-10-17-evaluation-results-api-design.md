---
comet_change: evaluation-results-api
role: technical-design
canonical_spec: openspec
archived-with: 2026-10-17-evaluation-results-api
status: final
---

# 评估结果查询与分析 API — 技术设计（Design Doc）

> 本文深化 open 阶段 `openspec/changes/evaluation-results-api/design.md`。canonical 需求以 OpenSpec delta spec 为准：`openspec/changes/evaluation-results-api/specs/api/evaluation-results/spec.md`。

## 1. 意图

issue #155 要求为已落库的评估结果提供查询、统计、对比、可视化数据、失败分析和报告导出。执行器已经把单元摘要写入 `evaluation_results`。本设计只增加读取 API，并在新写入的 metrics 中补上迭代次数。

## 2. 目标 / 非目标

**目标**

- 按 issue「API端点设计」提供路径。JSON 放在现有 `ApiResponse.data` 中。
- 详情、统计、对比、可视化和报告共用一套读时聚合。
- 新结果写入 `metrics.iterations`。
- 雷达图返回 issue 示例中的 `dimensions`、`series`、`problem_counts`。
- 所有者隔离与现有评估 API 相同。

**非目标**

- 不新建业务表，不把 Redis 当作正确性依赖。
- 不保存生成代码、沙箱输出或 LLM 轨迹。
- 不在查询时重新调用 LLM、沙箱或 `classify_failure_mode`。
- 不修改 CLI 报告的章节结构，不改现有按套件的学习曲线端点。
- 不使用 `src/capability.py` 的五维启发式。issue 示例的维度是 Array、Graph、Dynamic Programming、Greedy、Math、String、Other，对应 `capability_profiler.ALL_DIMENSIONS`。

## 3. 数据与聚合

`_record_unit_result` 在已有 metrics 中增加 `iterations`：值为 `unit.result["iterations"]` 的长度；该字段缺失或不是列表时写 0。不把轨迹列表本身写入 metrics。没有 `unit.result` 的失败行保持 `metrics is None`。

读取时的口径：

- 成功：结果行 `status == "success"`。分母是参与统计的单元数。
- 成本：跳过 `metrics.cost_unknown` 为真的单元，合计其余 `cost_usd`，并返回未知数量。
- 迭代：只聚合存在 `metrics.iterations` 的行。缺失记入未知数量，不显示为 0 或 1。平均值只除以已知行数。
- 执行时间：`avg_execution_time` 是该策略全部单元已保存 `execution_time_seconds` 的平均值。
- 难度过滤优先使用 `metrics.difficulty`，缺失时用 `problems.difficulty`。标签用 `problems.tags`。
- 路径参数先在当前用户的 `evaluations` 中匹配 `id`，再匹配 `run_id`。都没有则 404。不区分「不存在」和「属于别人」。

一个 `EvaluationResultsService` 提供这套聚合。路由只做认证、查询参数和响应外壳。

## 4. 端点与响应

路由文件 `api/routes/evaluation_results.py`，服务文件 `api/services/evaluation_results_service.py`。在 `api/main.py` 挂上该路由。全部端点使用 `current_user`。未登录返回现有认证错误。`ValueError` 且消息含 `not found` 时返回 404，与 A/B 路由相同。

分页参数 `limit` 默认 20，合法范围 1–100，越界回退 20。`offset` 小于 0 时按 0。排序只允许 `completed_at` 和 `created_at`，默认 `completed_at` 降序。

| 路径 | `data` |
| --- | --- |
| `GET /api/v1/results/{run_id}` | `run_id`、`status`、`created_at`、`completed_at`、完整 `strategies`、分页 `problems` |
| `GET /api/v1/results` | 当前用户的运行分页。`strategy`、`difficulty`、`tag` 保留至少有一个匹配单元的运行。`status` 过滤评估状态 |
| `GET /api/v1/results/problems/{problem_id}` | 该用户在这道题上的单元分页。`status` 过滤单元状态 |
| `GET /api/v1/analytics/success-rate` | 总体、按难度、按标签的成功率 |
| `GET /api/v1/analytics/tokens` | token 合计与平均 |
| `GET /api/v1/analytics/iterations` | 已知次数、未知数量、平均值，以及按次数的分布 |
| `GET /api/v1/analytics/failure-modes` | 已保存 `failure_mode` 的计数 |
| `GET /api/v1/compare/strategies` | 要求 `run_id`。各策略数字与该次详情一致 |
| `GET /api/v1/compare/models` | 按 `evaluations.model` 分组的同一聚合 |
| `GET /api/v1/compare/history` | 用 `run_id` 确定模型与策略集合。同一用户、同一配置、已完成、按完成时间排列。没有其他运行时为空序列 |
| `GET /api/v1/compare/ab-test/{test_id}` | `ABTestService.results` 的返回值 |
| `GET /api/v1/visualizations/success-rate-chart` | 每个策略一个成功率点 |
| `GET /api/v1/visualizations/token-chart` | 每个策略一条折线，点是各题 token |
| `GET /api/v1/visualizations/capability-radar` | issue 示例形状 |
| `GET /api/v1/visualizations/cost-accuracy` | 每个策略一点：成功率与 `estimated_cost_usd` |
| `GET /api/v1/visualizations/learning-curve` | 该用户已完成的 `benchmark_runs` |
| `GET /api/v1/failures/summary/{run_id}` | `failure_mode` 计数和错误聚类 |
| `GET /api/v1/failures/by-tag` | 每个标签的成功率、解出数、总数 |
| `GET /api/v1/failures/cases/{run_id}` | 非成功单元和已保存的 `error_message` |
| `GET /api/v1/reports/markdown/{run_id}` | `text/markdown` 文件 |
| `GET /api/v1/reports/csv/{run_id}` | `text/csv` 文件，UTF-8 BOM |
| `GET /api/v1/reports/html/{run_id}` | `text/html` 文件 |

统计、可视化和 `failures/by-tag` 接受可选查询参数 `run_id`、`strategy`、`difficulty`、`tag`。不传 `run_id` 时只统计该用户已完成的运行。传入 `run_id` 时只统计那一次运行，包括尚未完成的运行。

详情里每个策略包含 `name`、`success_rate`、`total_problems`、`solved_problems`、`avg_tokens`、`estimated_cost_usd`、`unknown_cost_count`、`avg_execution_time`、`by_difficulty`。`problems` 使用现有分页结构。每题包含 `problem_id`、`strategy`、`status`、`iterations`、`tokens`、`execution_time`。历史行没有 `iterations` 时该字段为 `null`。

静态路径 `results/problems/{problem_id}` 必须注册在 `results/{run_id}` 之前。

报告成功时返回文件正文和 `Content-Disposition`。404 使用现有 JSON 错误，不附带文件。没有单独的 PNG 路径。

## 5. 可视化、失败分析与报告

雷达把单元和题目组成 `calculate_dimension_scores` 能接受的 dict。dict 上的 `model` 使用 `evaluations.model`，这样 `series.name` 是模型名。分数和维度顺序来自 `format_dimension_scores_for_radar`。`problem_counts` 来自 `get_dimension_problem_counts`。没有题目的维度分数为 0。

学习曲线读取该用户 `status == "completed"` 的 `benchmark_runs`，按 `completed_at`、`id` 排序。每点包含 `suite_id`、时间、模型、准确率、成本。可选 `suite_id` 收窄范围。没有记录时返回 200 和空序列。`GET /api/v1/benchmarks/learning-curve/{suite_id}` 保持原样。

失败汇总按非成功单元已保存的 `failure_mode` 计数，并附带 `failure_category` 计数。聚类只对已保存的 `error_message` 调用 `normalize_message` 后计数。不调用 `analyze_results`，因为它会按消息重新分类并覆盖已保存模式。

Markdown 和 HTML 调用 `MarkdownGenerator.generate` 与 `HTMLGenerator.generate`。调用前在内存中构造 `ExecutionResult`：已保存字段填入，`generated_code` 为空字符串，不写入响应。迭代次数已知时，构造同等长度的空 `IterationResult`，只为满足 `len(iterations)`。这些对象不落库。生成器要求文件路径，调用时使用临时文件，返回生成器给出的字符串后删除临时文件。

HTML 中的 PNG 只来自 `ChartGenerator` 已有的成功率、token、迭代分布和能力雷达函数。函数返回空时保留生成器现有的图表不可用提示，不返回空图片。

CSV 使用 `CSVExporter` 的列名，但由本服务自己写。未落库的测试计数和隐藏测试计数留空。缺失 `iterations` 留空。不调用 `CSVExporter.export`，因为它会把空轨迹写成 1、把空测试列表写成 0。

## 6. 风险

- 历史行没有 `iterations`。迭代分布和平均值必须把它们算作未知。
- 报告不能回放 CLI 里的代码和沙箱轨迹。验收对齐的是成功率、解出数、token 和成本。
- 详情的策略汇总扫描该次运行的全部单元；题目分页不能提前截断这次扫描。
- 跨运行统计只包括已完成评估，避免把进行中的部分结果混进对比。

## 7. 测试

新测试 `tests/test_api_evaluation_results.py`，使用临时 SQLite 和 `TestClient`，直接插入两个用户的评估、结果和带标签题目。不调用真实 LLM，不连接 Redis。

覆盖：3 成功 1 失败得到 0.75；他人 id 与 `run_id` 为 404 且不出现在列表；标签过滤后的 `total`；未知成本不进美元合计；缺失迭代次数为未知；策略对比与详情一致；空历史对比；雷达维度、分数范围和 `problem_counts`；空学习曲线；失败模式不被改写；失败案例只有非成功单元；Markdown 与 JSON 的成功率和解出数相同；他人 CSV 为 404 且无文件正文；未登录为 401；详情分页不改变策略汇总。

写入测试调用 `_record_unit_result`：2 轮轨迹得到 `metrics.iterations == 2`，且 metrics 中没有生成代码或沙箱输出。

覆盖率命令针对新增路由、查询服务和 `_record_unit_result` 所在模块，阈值 80%。现有离线套件保持通过。
