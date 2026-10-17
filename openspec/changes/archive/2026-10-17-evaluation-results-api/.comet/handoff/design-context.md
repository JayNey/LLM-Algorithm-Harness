# Comet Design Handoff

- Change: evaluation-results-api
- Phase: design
- Mode: compact
- Context hash: ac658f6acf662aa0431b06a6cb4e52bd2ef97830279a834617e119a8ef6bd7a5

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/evaluation-results-api/proposal.md

- Source: openspec/changes/evaluation-results-api/proposal.md
- Lines: 1-27
- SHA256: 0e17b02a29e28fb122c13b43e814d3e80fd21b693f90a78ac0dfc8e5ab4411ab

```md
## Why

Issue #155 要求为已完成的评估提供查询、统计、对比、可视化和报告导出 API。评估执行已经把每个（策略 × 题目）单元写入 `evaluation_results`，但 API 目前只能看到任务状态和聚合计数，前端无法按任务、题目、策略或模型读取结果。

## What Changes

- 新增 owner 作用域的结果查询：单个任务详情、分页列表、题目历史，以及按策略、难度、标签过滤。
- 新增统计分析：成功率、token、迭代次数、执行时间、失败模式。口径与该次运行已落库的单元结果一致，不重新执行评估。
- 新增对比：策略对比、模型对比、同一配置的历史对比；A/B 结果复用现有 A/B 测试服务。
- 新增可视化数据：成功率、token、迭代分布、能力雷达、成本-准确率、学习曲线。雷达分数沿用 `src/reporting/capability_profiler.py` 的维度与 0–100 分口径。
- 新增失败分析：按已落库的 `failure_mode` / `failure_category` 与错误信息汇总，错误聚类沿用 `src/error_analysis.py` 的归一化规则。
- 新增报告导出：Markdown、CSV、HTML，以及现有 `ChartGenerator` 已支持的 PNG。
- 单元落库补记迭代次数，供迭代统计和分布图使用。不保存完整沙箱轨迹或生成代码。

## Capabilities

### New Capabilities

- `api/evaluation-results`: 评估结果的查询、统计、对比、可视化数据、失败分析和报告导出。

### Modified Capabilities

无。现有记录、雷达图和错误分析规格的 CLI 行为不变；本 change 只增加 API 消费方式和一个落库计数字段。

## Impact

影响 `api/`（新路由与服务）、`src/tasks/evaluation.py` 的单元度量写入，以及 `API.md`。不新增业务表，不把 Redis 作为正确性依赖。分析与报告模块只被调用，不改其 CLI 产物契约。

```

## openspec/changes/evaluation-results-api/design.md

- Source: openspec/changes/evaluation-results-api/design.md
- Lines: 1-18
- SHA256: eb61e21b7eca2f8c383706a5606fe9e495950a235a1509c69076a1048fcbf46a

```md
# 设计说明：evaluation-results-api

## 决策

1. **读已落库结果，不重跑评估**。查询、统计、对比和报告都从 `evaluations`、`evaluation_results` 与 `problems` 计算。成功以结果行 `status == "success"` 为准，并与 `metrics.success` 保持一致。
2. **沿用现有 API 外壳**。响应使用 `ApiResponse` / `PaginatedData`，认证与 owner 隔离与评估端点相同。路径参数接受该用户的 `evaluation.id` 或 `evaluations.run_id`。他人资源返回 404。
3. **补记迭代次数，不补记轨迹**。`_record_unit_result` 在 `metrics` 中写入 `iterations`（执行轨迹长度；无轨迹则为 0）。不把生成代码、沙箱输出或 LLM trace 写入结果行。失败模式优先读已保存的 `failure_mode` / `failure_category`；错误聚类只对已保存的 `error_message` 调用 `error_analysis`。
4. **统计与报告共用一套聚合**。成功率、题量、token、成本、耗时只实现一次。成本合计跳过 `cost_unknown` 的单元，并在响应中标出未知成本的数量，不把未知成本当成 0 美元去触发对比结论。
5. **可视化返回数据，PNG 只走现有图表函数**。JSON 图表供前端绑图。PNG 仅当 `ChartGenerator` 已有对应函数时生成。能力雷达的维度顺序和 0–100 分使用 `capability_profiler`，API 再映射为 issue 中的 `dimensions` / `series` / `problem_counts`。
6. **A/B 与学习曲线不另起算法**。`/compare/ab-test/{test_id}` 返回现有 A/B 结果服务的数据。学习曲线读取该用户已完成的 `benchmark_runs`；没有历史时返回空序列。
7. **正确性不依赖 Redis**。列表分页（默认 20，最大 100）加上现有索引满足查询。缓存可以后加，但测试与接口在无 Redis 时必须给出相同结果。

## 非目标

- 修改 CLI 报告的章节结构或雷达图 PNG 的绘图样式。
- 为结果查询新增业务表或跨库外键。
- 在 API 进程内重新调用 LLM 或沙箱。
- 用未落库的隐藏测试输入重新分类失败。

```

## openspec/changes/evaluation-results-api/tasks.md

- Source: openspec/changes/evaluation-results-api/tasks.md
- Lines: 1-21
- SHA256: bb53f25cf42910955015b7e60cc7a7578299d000385b8e7eaf2859c617ef8602

```md
## 1. 结果读取与落库补齐

- [ ] 1.1 单元结果写入 `metrics.iterations`；已有行的统计在字段缺失时按未知处理，不回填伪造值
- [ ] 1.2 结果查询服务：按 owner 解析 evaluation id / run_id，分页列出结果，支持策略、难度、标签、状态过滤

## 2. 查询、统计与对比 API

- [ ] 2.1 `GET /api/v1/results/{run_id}`、`GET /api/v1/results`、`GET /api/v1/results/problems/{problem_id}`
- [ ] 2.2 成功率、token、迭代、耗时、失败模式统计端点，与详情聚合共用计算
- [ ] 2.3 策略、模型、历史对比；A/B 对比复用现有结果服务

## 3. 可视化、失败分析与报告

- [ ] 3.1 成功率、token、能力雷达、成本-准确率、学习曲线的 JSON 数据
- [ ] 3.2 失败汇总、按标签弱项、失败案例列表；错误信息按现有归一化规则聚类
- [ ] 3.3 Markdown、CSV、HTML 与现有图表函数可生成的 PNG 导出

## 4. 验证

- [ ] 4.1 API 测试覆盖查询隔离、统计口径、空历史、未知成本和报告导出；不连接真实 LLM 或 Redis
- [ ] 4.2 更新 `API.md`，并记录与 CLI 聚合一致的检查结果

```
