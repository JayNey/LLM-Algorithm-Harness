## Context
LLMClient 已发布实例累计快照，共享监控数据库覆盖同一实例快照并汇总计数。

## Goals / Non-Goals
完成现有跨 Worker 统计的明确口径与回归覆盖，不引入群集发现或新的公开 API。

## Decisions
- 命中率为 sum(hits)/(sum(hits)+sum(misses))，避免请求量不同的实例命中率算术平均。
- 零查询返回 null，禁用缓存的调用不构成缓存查询。
- 重复实例快照覆盖，过期实例退出聚合，保留 cluster_complete=false。
- 沿用共享 AUTH_DATABASE_PATH 前提，容量新鲜度不改变计数范围。

## Risks / Trade-offs
保留期限及数量上限会移除历史计数；文档说明这是保留实例生命周期计数，不是保留时间窗口内的请求统计。
