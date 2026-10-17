# Brainstorm Summary

- Change: evaluation-results-api
- Date: 2026-10-17

## 确认的技术方案

用户已确认整份设计。读时聚合：一个查询服务从 `evaluations`、`evaluation_results` 和 `problems` 现场计算。路径按 issue #155「API端点设计」。JSON 放在 `ApiResponse.data`。新写入只补 `metrics.iterations`。雷达走 `capability_profiler` 并映射为 issue 示例。失败模式读已保存字段，聚类用 `normalize_message`。Markdown/HTML 调用现有生成器。

## 关键取舍与风险

不建新表，正确性不依赖 Redis。历史行缺少 `iterations` 时记为未知。报告与 CLI 在汇总数字上对齐，轨迹正文和生成代码不在这次 API 里。`src/capability.py` 的五维启发式不用于该雷达，因为 issue 响应示例的维度是 `capability_profiler.ALL_DIMENSIONS`。

## 测试策略

`tests/test_api_evaluation_results.py` 用 SQLite 夹具和 TestClient 覆盖 owner 隔离、统计口径、未知成本、缺失迭代次数、空历史和报告导出。不连接真实 LLM 或 Redis。新增路由、查询服务和迭代次数写入的覆盖率目标大于 80%。

## Spec Patch

确认设计后回写：

- 详情的策略汇总覆盖全部单元，并包含 `avg_execution_time`；题目列表只返回当前页。
- CSV 对未落库的测试计数和缺失的 `iterations` 留空。
