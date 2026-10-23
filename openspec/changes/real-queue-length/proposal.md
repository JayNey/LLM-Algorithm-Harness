## Why

现有 Redis 健康仅检查 PING，数据库 pending 和 worker reserved 均不能代表 broker 中等待执行的消息数，管理员无法判断真实积压。

## What Changes

- 在现有 Redis 探针补充已配置队列的等待消息计数和总数，覆盖优先级分桶及 transport 前缀。
- 在既有 system/status 分别展示 broker_queue、database_pending、worker_reserved，保留原字段。
- 复用启用开关、总超时、缓存、权限与安全错误投影；未知数值保持 null。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `async-task-queue`：补充异步队列的三类独立监控计数。

## Impact

现有 api/monitoring 队列探针、监控路由、回归测试和监控文档。不新增端点、依赖或数据库 schema。
