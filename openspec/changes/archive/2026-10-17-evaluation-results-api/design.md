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
