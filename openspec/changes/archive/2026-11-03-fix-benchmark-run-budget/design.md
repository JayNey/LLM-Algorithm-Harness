## Context

基准运行由 `BenchmarkService._execute` 构造 `HarnessConfig` 并调用 `BenchmarkExecutor.execute`，执行器创建 `AlgorithmHarness` 后调用 `harness.run()`（非 task-service 路径）。`HarnessConfig.budget_cap_usd` 被原样传入，但 `AlgorithmHarness.run()` 对该路径直接拒绝预算，于是 worker 异常、run 置为 failed。

基准现有的暂停/取消依赖注入到 harness 的 `should_pause` 回调（检查 AsyncTask 状态与 `BudgetGuard`），暂停后由 `BenchmarkService` 把 run 与任务置为 `paused`，检查点目录为 `results/benchmarks/api/{run_id}/units`。

## Decisions

- **继续走非 task-service 路径，在 harness 内实现 auto_stop 运行级预算。** task-service 路径会创建独立的 TaskService 记录、使用 CLI 进度条，并绕过基准的 `should_pause` 回调，与现有 API 暂停/取消和检查点语义冲突。非 task-service 路径只需复用已有 `RunCostMonitor`，改动面更小。
- **非 task-service 仅接受 `auto_stop`。** 降级（downgrade）依赖难度到策略的映射，基准请求没有该字段；成本预警配置也未在基准接口暴露。遇到不支持的组合仍返回明确错误，不静默忽略。
- **成本累计使用 `result_cost` 的已知定价口径。** 每完成一个题目单元即把结果结算进 `RunCostMonitor`；达到上限后置 `paused`，循环在下一单元派发前停止。未知用量不当作免费，与现有预算语义一致。
- **检查点重放的结果也计入累计。** 恢复运行会重放已完成题目；若不计入，恢复后可再次花超上限，违反“预算仍不足则继续暂停”的预期。重放单元只结算成本、不重复执行。
- **暂停后的状态流转复用现有实现。** `BenchmarkService` 已能把 `executor.paused` 映射为 run/任务 `paused`；本次只负责让预算触发该标志，不新增状态或接口。

## Risks / Trade-offs

- 达到上限发生在单元边界，在途调用仍可能超过上限；与现有个人预算和 CLI auto_stop 口径一致。
- 未知成本结果只记录未知计数，不虚构金额，因此“已知成本”是下限而非精确总额。
- 非 task-service 路径新增预算监测，若未来实验/A/B 也在该路径使用 `budget_cap_usd`，会共享 auto_stop 语义；当前它们使用 per-problem `BudgetTracker` 或各自 runner，不受影响。

## Migration Plan

无需数据迁移。Worker 部署后对新的及恢复的基准运行生效；回滚 worker 即恢复原行为。前端无需改动。
