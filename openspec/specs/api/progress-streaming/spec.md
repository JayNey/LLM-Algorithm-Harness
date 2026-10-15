# api/progress-streaming Specification

## Purpose
TBD - created by archiving change websocket-progress. Update Purpose after archive.

## Requirements

### Requirement: 进度事件发布

评估任务 worker SHALL 在状态转换与单元完成节点向 Redis 频道 `progress:{task_id}` 发布 JSON 事件（`task.started`、`task.progress`、`problem.completed`、终态事件）；Redis 不可用时 SHALL 降级为仅记录日志，绝不影响任务执行。

#### Scenario: Redis 故障不阻塞任务

- **WHEN** 发布事件时 Redis 连接失败
- **THEN** 发布调用不抛异常，任务照常推进至终态

### Requirement: WebSocket 订阅与鉴权

系统 SHALL 提供 `/api/v1/ws/progress` WebSocket 端点：连接须携带有效访问令牌（无效则关闭 4401）；`subscribe` 动作校验任务归属（非本人任务关闭 4403），成功后发送当前任务快照并转发该任务的实时事件；`unsubscribe`/`ping` SHALL 按协议响应。

#### Scenario: 仅任务所有者可订阅

- **WHEN** 用户 B 订阅用户 A 的任务
- **THEN** 连接以 4403 关闭，收不到任何事件

#### Scenario: 订阅即得快照

- **WHEN** 用户订阅自己已在运行的任务
- **THEN** 首条消息为该任务当前状态快照（status + 计数），随后收到后续实时事件

#### Scenario: 无效令牌被拒

- **WHEN** 携带无效令牌建立 WebSocket 连接
- **THEN** 连接以 4401 关闭
