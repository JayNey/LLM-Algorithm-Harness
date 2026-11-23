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

系统 SHALL 提供 `/api/v1/ws/progress` WebSocket 端点：连接须携带有效访问令牌（无效则关闭 4401）；`subscribe` 动作校验任务归属（非本人任务关闭 4403），成功后发送当前任务快照并转发该任务的实时事件；`unsubscribe`/`ping` SHALL 按协议响应。连接 SHALL 在处理客户端动作、发送评估快照和转发实时事件前核验建连凭据的有效性，并至少每秒检查一次持续连接；会话撤销或访问令牌到期后 SHALL 以 4401 关闭连接、停止数据发送并释放全部订阅及后台任务，即使没有客户端动作或进度事件也 SHALL 在一个检查周期内关闭。

#### Scenario: 仅任务所有者可订阅

- **WHEN** 用户 B 订阅用户 A 的任务
- **THEN** 连接以 4403 关闭，收不到任何事件

#### Scenario: 订阅即得快照

- **WHEN** 用户订阅自己已在运行的任务
- **THEN** 首条消息为该任务当前状态快照（status + 计数），随后收到后续实时事件

#### Scenario: 无效令牌被拒

- **WHEN** 携带无效令牌建立 WebSocket 连接
- **THEN** 连接以 4401 关闭

#### Scenario: 注销后旧连接发起订阅

- **WHEN** WebSocket 对应的会话已注销，旧连接发起新的或重复的订阅
- **THEN** 连接以 4401 关闭，不发送评估快照或订阅确认，并释放已有订阅

#### Scenario: 注销后既有订阅收到事件

- **WHEN** 已订阅连接对应的会话已注销，任务产生新的进度事件
- **THEN** 连接以 4401 关闭，不转发该事件，并释放全部订阅

#### Scenario: 密码变更保留现有会话

- **WHEN** 已登录用户成功变更密码，原有会话仍有效
- **THEN** 已建立的 WebSocket 继续按有效会话工作；后续注销该会话时连接以 4401 关闭并释放全部订阅

#### Scenario: 访问令牌到期

- **WHEN** 已建立 WebSocket 使用的访问令牌到期，但底层会话仍存在
- **THEN** 连接以 4401 关闭，不再接收评估数据，并释放全部订阅

#### Scenario: 空闲连接检查失效凭据

- **WHEN** 已建立 WebSocket 的会话被撤销或访问令牌到期，且客户端和任务没有发送任何消息
- **THEN** 连接在一个检查周期内以 4401 关闭，并释放全部订阅及后台任务

#### Scenario: Cookie 认证连接遵守会话失效

- **WHEN** 使用访问 Cookie 建立的 WebSocket 对应会话被注销
- **THEN** 连接以 4401 关闭，不再接收评估数据，并释放全部订阅
