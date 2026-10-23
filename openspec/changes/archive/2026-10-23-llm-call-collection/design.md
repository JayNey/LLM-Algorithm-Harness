## Context

LLMClient._call_with_retry 是 OpenAI（含 local/SiliconFlow）与 Anthropic 两条真实生成请求的共同入口；缓存命中在进入 provider 路径前返回，list_models/check_connection 不经过该入口。API MonitorService.llm_stats 当前为占位。API 与 Celery worker 是独立进程，进程内计数无法让已有监控端点读取 worker 的真实请求。

## Goals / Non-Goals

实现部署内共享认证数据库的真实请求采集与查询，保留原模型响应、异常脱敏与重试语义。统计单位为已结束的一次 SDK 生成请求尝试，不含缓存、本地响应解析、退避等待或采集写入耗时。请求成功表示 SDK 返回，不表示生成的代码通过评测。不增加 provider 费用，不改变缓存和重试设置。

## Decisions

1. 在每次 operation() 周围使用单调时钟计时；成功、异常分别采集一次。采集入口和结束计时均隔离故障，保证监控错误不改变原业务结果。
2. 复用 api_monitor_meta 的固定命名空间键，以 SQLite 单事务更新调用总数、成功数、失败数、总耗时及起始时间；读取也使用一致性快照。避免按每次请求新增无限增长记录，不新增表或迁移。
3. worker 按已有 AuthSettings 解析同一数据库；写入只传布尔结果和有限非负毫秒数，不传 prompt、响应正文、模型名、URL、密钥或原始异常。采集模块延迟加载，命令行缺少服务端配置时不阻断请求。
4. 现有 llm-stats 返回 total_calls、successful_calls、failed_calls、success_rate、avg_latency_ms 和明确的累计起点/共享数据库范围；零样本的成功率及平均耗时为 null。保留独立的 recorded_usage_hooks 与 key_verification_count。
5. 聚合代表启用采集以来成功写入此数据库的已完成请求，重启后保留，不声称覆盖部署前历史、未配置 CLI、进程被强杀或采集故障时丢失的请求；响应与文档明确 best-effort 口径。

## Risks / Trade-offs

- SQLite 写入竞争 → 单次短事务、有限连接等待，采集失败隔离；测试验证多连接并发不丢更新。
- API 与 worker 配置不同 → 文档明确必须共享 AUTH_DATABASE_PATH，跨连接测试验证读取一致。
- 请求中途进程终止 → 累计只表示已完成且成功采集的请求，不把它表述为全部署精确总账。

## Workflow Decision

用户已选择独立分支 codex/tweak/20261023/llm-call-collection。调查确认需要新增 capability api/llm-call-metrics 并连接真实模型客户端与跨进程监控存储，命中 comet-tweak 升级判定；用户明确选择继续 tweak，按单一 change 完成采集、查询、测试与文档（含超过六个文件的预期改动），不升级 full。短事务将 busy_timeout 设为 100ms；连接初始化缓存包含 PID、数据库路径和监控保留配置，避免 prefork 和不同配置混用。
