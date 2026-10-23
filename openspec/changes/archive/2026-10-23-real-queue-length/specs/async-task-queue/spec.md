## ADDED Requirements

### Requirement: 队列积压按来源独立展示

管理员监控 SHALL 只读采集配置的 Redis broker 中各业务队列等待执行的消息数量，覆盖所有配置的优先级分桶及键前缀，并返回每队列数量及总数。系统状态 SHALL 分别展示 broker_queue、database_pending 和 worker_reserved；数据库 pending 来自持久化 AsyncTask，worker reserved 只来自回复的 worker，三者不相加也不互相推算。探测 SHALL 遵循现有启用开关、总超时和缓存；失败、未启用、配置非法或不支持 transport 时等待数 SHALL 为 null，真实空队列 SHALL 为 0。采集 SHALL NOT 消费消息、读取任务内容、修改业务状态或暴露凭据。

#### Scenario: 多队列优先级积压
- **WHEN** 已配置的两个 Redis 队列在不同优先级分桶分别有 3 和 2 条消息
- **THEN** 返回各队列 3 和 2，总数 5，不计入未配置的队列和 unacked

#### Scenario: 独立展示三类计数
- **WHEN** broker 等待数为 5，数据库 pending 为 7，回复 worker reserved 为 2
- **THEN** system/status 分别返回 5、7、2，不将其中任一值作为其他指标或总积压

#### Scenario: 探测故障或关闭
- **WHEN** broker 超时、不可用、配置非法、不支持 transport 或未启用探测
- **THEN** broker 等待数为 null，且不泄露连接信息，数据库与 worker 的独立计数语义保持不变

#### Scenario: 空队列
- **WHEN** Redis 正常且所有配置队列均为空
- **THEN** 每队列及总等待数为 0，探测不创建或消费任务消息
