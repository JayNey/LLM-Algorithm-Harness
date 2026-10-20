## 方案

- MonitorSettings 增加显式启用开关、总超时和独立队列缓存 TTL。默认关闭，避免部署前未经选择访问 broker；禁用时保留明确 not_checked。
- QueueProbes 从实际 celery_app 的 broker 配置取连接信息；每类探测最多一个子进程。凭据只经 stdin 传入，不进入命令行、响应、错误或日志；stdout 仅安全 JSON。父进程限制执行时间，超时杀死并回收；关闭时取消进行中的子进程。DNS、连接、重试、读取都在此边界内。
- 单独 Redis 客户端执行 PING，不读取队列/结果。Celery 客户端使用独立连接，广播只读 monitoring_snapshot，worker 仅返回 active/reserved/concurrency 数值；reserved 排除 active。响应中使用 worker 名的摘要 ID，避免回显主机名或自由文本。没有提供的数值为 null。
- 不使用 inspect.active/reserved/stats，因为这些接口会返回参数、任务 ID 或连接配置。旧 worker 的未知命令回复标记 partial；没有回复标记 unknown。结果只描述截止时间内收到的 worker 回复，最大回复数量达到上限时标记 partial。
- 缓存采用单调时钟并标注 age/cached；缓存过期不会把旧健康结果冒充当前值。并发刷新直接返回 unknown/in_progress，避免排队放大超时。system/status 复用同一次 workers 结果。
- 真实评估实现标为 algorithm_harness，运行时模型、沙箱和凭据就绪未验证时 real_evaluation_available 为 null。无 async 关联的 Evaluation 标记 unassigned_or_legacy。未接入指标属于 #157，不继续引用已完成 #149。

## 验证

覆盖真实子进程超时/回收、并发缓存/关闭、故障与畸形回复、数值过滤与凭据不可见、管理员权限、业务库零状态写入。通过临时隔离的 Redis 容器和 Celery worker 验证真实链路，不提交业务任务或调用提供商。常规离线测试不依赖 Redis 服务。独立审查后执行质量门禁和全量离线测试，保持 90% 覆盖率要求。
