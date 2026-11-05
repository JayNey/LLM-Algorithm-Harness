## Context

BudgetTracker.record 在响应后增加 calls，异常路径漏记。Self-Consistency 的通用异常处理吞掉 BudgetExhausted。

## Goals / Non-Goals

实现每题逻辑调用上限；不将 max_calls 改为远程收费或 SDK attempt 限额。

## Decisions

allow_call 保持只读检查语义；包装器准入后、进入 inner 前记录 calls，record 只结算响应用量。失败不退还名额，成功不重复计数。无预算时仍记账；未 begin_problem 时保持透传。

缓存命中也算一次逻辑 generate；LLMClient 内部有界 SDK retries 属于同一次逻辑调用，由 retry_max_attempts / retry_max_elapsed_seconds 限制。文档与字段说明显式说明放大关系。

Self-Consistency 单独捕获 BudgetExhausted，退出候选循环，投票保留已有结果，调用 mark_budget_exhausted 统一终态与失败分类。

## Risks / Trade-offs

失败请求没有可靠 token 信息时不虚构 token 或费用。BudgetTracker 仍按已有单题串行使用约定工作。
