## Context

见 proposal.md。现有历史存储按策略 accuracy 的算术平均提取整体准确率，策略级 total_cost 来自 StrategyReport.estimated_cost_usd。API 的数据库字段和响应已包含 accuracy/cost_usd。

## Goals / Non-Goals

让既有执行器输出可直接被 API 记录，并确保学习曲线完整消费记录。无需新增能力、端点、数据库迁移或架构协调；历史空值的批量修复不在范围内。

## Decisions

- 保留 suite、problems_evaluated、problems_missing、strategies 及其字段，在执行器结果顶层增加 accuracy 和 cost_usd。accuracy 使用各策略准确率的算术平均，与 BenchmarkHistoryStorage 保持一致；cost_usd 为各策略成本之和。无策略结果时 accuracy 为 None、cost_usd 为 0.0。
- API 优先记录顶层指标，仅在值为 None 时使用 summary 同名字段。逐字段判断，避免有效 0.0 被替换，同时兼容已有仅 summary 的调用方。
- 离线测试只替换外部 AlgorithmHarness 执行，不替换 BenchmarkExecutor 的输出映射；验证真实执行器输出经过 API 持久化后，详情与学习曲线一致。

## Risks / Trade-offs

- 策略权重沿用历史存储的等权口径；不把同一题在多策略中的尝试视为独立题目。
- 已有数据库记录中的空指标保持不变；本次修复影响后续新运行。
- 用户已选择隔离方式 2：在 tweak/20261026/fix-benchmark-statistics 分支实现，目标分支 main。
