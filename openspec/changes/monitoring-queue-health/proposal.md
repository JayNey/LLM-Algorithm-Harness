## Why

#157 的监控基础已合并，#149 已接入真实执行，但队列健康和 worker 负载仍固定返回 not_checked，且多处仍标为 mock。需要在管理员端点中提供有界、可验证的实际观测。

## What Changes

- 操作者显式启用队列探测；读取当前 Celery broker 配置，探测 Redis PING 与 worker 数值负载。
- 使用只返回计数的 Celery inspect 命令，不查询任务参数、任务 ID、主机路径或完整 worker stats。
- 网络观测在受硬超时约束的子进程完成，限制并发、回复数量、输出大小，缓存结果并在关闭时清理。
- 区分禁用、失败、超时、无回复、旧 worker 不支持以及成功；只统计回复 worker，不声称发现全部集群或 Redis 等待队列长度。
- 更新过时 mock/#149 状态与文档，保留真实 LLM 性能、容器指标和新配额为 #157 后续范围。本 PR 使用 Refs #157。

## Capabilities

### New Capabilities
- `api/queue-health`: 管理员队列健康、worker 数值负载和有界生命周期。

### Modified Capabilities

无。

## Impact

api/monitoring、已有监控路由、Celery worker include 配置、回归与部署文档。沿用当前依赖，不新增 HTTP 路由，不修改业务任务状态和数据库 schema。
