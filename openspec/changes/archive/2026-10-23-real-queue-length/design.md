## Context

参见 proposal.md。既有 QueueProbes 通过隔离子进程执行 Redis/Celery 探测，现有 system/status 已有数据库和 worker 观测。

## Decisions

- QueueProbes 在父进程快照实际 Celery 队列与 Redis transport 配置，经 stdin 传入子进程；不扫描 broker 键空间。仅传递观测需要的 priority_steps、sep、global_keyprefix。
- Redis PING 保留原义；附加独立 broker_queue 结果。队列计数失败不将成功 PING 变为失败，队列结果独立标记 unknown。子进程整体超时仍由既有父进程回收。
- 使用 Redis 只读 LLEN pipeline(transaction=False) 读取配置队列各优先级键，尊重 Kombu 的 key 规则。不读取 unacked、消息正文或结果后端。限制队列、分桶和名称长度；错误不返回自由文本。
- system/status 复用 health 中同一次 Redis/worker 观测，在 queue_metrics 中独立展示 broker_queue、database_pending、worker_reserved。数据库无样本时为 0，失败时 null。

## Risks / Trade-offs

- Redis 与数据库、worker 的观测非原子且可能缓存；各项保留来源和状态，不计算合计。
- 等待数仅覆盖配置的业务队列，不声称覆盖整个 Redis 实例；worker 已接收的 ETA/unacked 不在计数内。
- 沿用 MONITOR_QUEUE_PROBES_ENABLED；默认关闭。部署无需迁移，可回退现有 API 代码。
