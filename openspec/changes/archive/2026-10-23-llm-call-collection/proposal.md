## Why

真实模型请求尚未接入调用监控，现有 llm-stats 只能返回占位值。密钥验证和使用登记次数无法代表真实生成调用的成功率或耗时。

## What Changes

- 在真实 provider 生成请求执行处采集调用次数、成功/失败和单调时钟耗时；明确每次重试单独计数，缓存命中和连通性验证不计入。
- 接入已有 LLM 统计查询，明确统计范围、无样本语义和可用性；采集失败不得影响模型调用结果。
- 增加成功、失败、重试、缓存命中及采集故障的验证，并更新监控文档。

## Capabilities

### New Capabilities
- `api/llm-call-metrics`：真实生成请求的次数、结果及耗时采集，跨进程共享已记录的聚合统计。

### Modified Capabilities
无。已核对 capability inventory、LLM 缓存规范和真实评估执行规范；当前没有独立的 LLM 调用监控规范。

## Impact

涉及 LLMClient、监控采集/查询、相关测试与监控文档。复用现有监控 SQLite 元数据表，不新增 HTTP 路由或数据库表。工作区隔离已由用户选择独立分支。
