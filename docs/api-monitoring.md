# API 系统监控基础能力（#157）

系统提供管理员授权、本机资源和 Docker 预检、持久化请求统计、安全日志、配置及已有配额查询。#149 已完成异步执行接线，评估 worker 使用 AlgorithmHarness。队列监控可显式启用 Redis 连通性与 Celery worker 数值负载探测；真实 LLM 时延、任务执行指标、容器资源和新配额仍是 #157 后续范围。

## 配置管理员

先按 [认证指南](api-authentication.md) 设置签名与加密密钥，注册并登录一个用户，通过 `GET /api/v1/users/me` 获取其 `data.id`。由部署者将这个 UUID 写入环境变量或受保护的 `.env`，然后重启服务：

```bash
# 替换为已经注册的用户 UUID；这是部署配置，不是新建管理员账号。
export MONITOR_ADMIN_USER_IDS='["11111111-1111-4111-8111-111111111111"]'
./run_api.sh
```

默认白名单为空。管理员仍需正常登录并传递 `Authorization: Bearer <access_token>`，会话撤销和受保护请求限流继续生效。没有有效身份返回 401；普通用户访问系统级端点返回 403。注册、资料更新和 Token 中的客户端角色声明不能赋予管理员权限。此配置只授予下述监控端点的权限，不提供通用角色管理接口。

可配置项及默认值：

- `MONITOR_ADMIN_USER_IDS`：JSON UUID 数组，默认 `[]`。
- `MONITOR_RETENTION_SECONDS`：604800（7 天），范围 60–2592000。
- `MONITOR_MAX_ROWS`：10000，范围 100–100000；请求表、日志表分别限制行数。
- `MONITOR_API_WINDOW_SECONDS`：60，范围 1–86400；综合性能端点使用的 API 统计窗口。
- `MONITOR_PROBE_CACHE_SECONDS`：5，范围 0–300；Docker 预检结果缓存时间，0 表示不复用结果。
- `MONITOR_QUEUE_PROBES_ENABLED`：false；true 才进行队列网络探测。
- `MONITOR_QUEUE_TIMEOUT_SECONDS`：3，范围 0.5–10；每种探测从启动子进程到收集回复的时间预算。system/health 最多依次执行 Redis 和 worker 两种探测，因此队列部分最多约两倍预算，另含进程终止清理。
- `MONITOR_QUEUE_CACHE_SECONDS`：5，范围 0–300；每 API 进程的队列观测缓存，0 表示关闭缓存。
- `MONITOR_SANDBOX_IMAGE`：`python:3.11-slim`；仅接受受控 Docker 镜像引用。
- `MONITOR_SANDBOX_TIMEOUT_SECONDS`：5，范围 1–30；Docker 预检中的单个用例执行超时。

请求和日志保存在现有认证 SQLite 的 `api_monitor_*` 表中，复用 `AUTH_DATABASE_PATH`。统计起点与清理水位持久化，同机多进程共享同一数据库时共享这些记录。评估任务保存在 #151 的业务数据库，由 `DATABASE_URL` 配置，默认是 `data/business/business.sqlite3`；它与认证和文件元数据 SQLite 独立。业务 SQL 指标、本机资源及缓存实例各有自己的作用范围，详见下文。

## 健康与资源端点

公开的 `GET /api/v1/health` 仅表示 API 存活，响应包含 `scope=api_liveness_only`。它不执行 Docker 探测，也不代表队列或业务数据库可用。

以下端点全部需要管理员身份，成功响应使用现有 `success/data/message` 包装：

- `GET /api/v1/system/health`：已探测组件全部为 ok 时返回 healthy；存在 unavailable/unknown 时为 degraded；禁用、未检查或部分回复为 partial。默认不探测 Docker；include_sandbox=true 可加入预检。pending_issues=[157] 表示监控尚有后续能力，不再引用已完成的 #149。healthy 只覆盖本次探测和收到回复的 worker，不证明全部集群或提供商可用。
- `GET /api/v1/health/database`：对实际认证/文件 SQLite 执行 `SELECT 1`，并验证所需表可查询；`business_database` 使用已绑定的评估服务 engine 检查实际连接、业务表与 Alembic revision，返回 `status/backend/required_tables/migration/read_only/latency_ms`。迁移检查按仓库 Alembic 元数据的 heads 比对数据库当前 heads，成功时通过 `migration.status/revisions/expected_heads` 说明版本一致；不一致时标记故障，不回显数据库中的任意版本文本。探测只读，不运行迁移、不创建评估服务，也不修改任务状态；不返回连接串、主机路径或凭据。任一已配置数据库检查失败时，总体状态为 `unavailable`。
- `GET /api/v1/health/redis`：显式启用后对实际 Celery broker 执行 Redis PING，返回 status/latency_ms/reason/cached/age_seconds，scope=configured_celery_broker。支持 redis/rediss；其他 transport 为 unsupported。只检查 broker，未单独检查 result backend。
- `GET /api/v1/health/workers` 与 `/api/v1/system/workers`：通过只读 monitoring_snapshot 命令返回 worker_count、workers、active、reserved、concurrency。仅统计截止时间内回复的 worker，scope=responding_celery_workers、cluster_complete=false；worker_id 是节点名称的稳定 SHA-256 摘要，不返回主机名。reserved 排除 active，只表示已被这些 worker 接收的待执行任务，不是 broker 队列长度。concurrency 来自池报告的 num_processes；不据此推导 CPU 利用率。
- `GET /api/v1/health/sandbox`：复用实际 `SandboxExecutor.health_check()` 执行 Docker 预检，失败为 `unavailable`。只使用 Docker；不可用时不回退 host，不返回异常中的主机路径或凭据。
- `GET /api/v1/system/resources`：CPU、内存、上传目录所在文件系统的磁盘用量，以及已登记且未标记删除的文件数量/字节。
- `GET /api/v1/system/status`：当前 API 进程运行时间、旧评估与异步任务各自的全量状态计数、基础健康与本机资源。旧来源保留 `task_counts/task_count/task_status/task_source`，来源值为 `persisted_business_evaluations`；异步来源新增 `async_task_counts/async_task_count/async_task_status/async_task_source`，来源值为 `persisted_async_tasks`。两组分别读取，不受分页限制，不提供相加后的全局原子快照；一组故障时只将该组计数标记为 `null`，状态为 `unavailable`。响应另含 `evaluation_worker_implementation=algorithm_harness`、`real_evaluation_available=null`。容器级资源采集默认 `not_configured/disabled`，可按下文显式启用，只观察当前 API Docker context 中带固定标签的运行沙箱。
- `GET /api/v1/system/tasks/running` 和 `/api/v1/system/tasks/queued`：分别查询所选持久化来源中 `running` 和 `pending` 状态的任务；`queued` 只表示数据库记录的 `pending` 状态，不能当成 Redis 队列长度。

任务查询支持 `task_source/limit/offset`：

- `task_source=legacy_evaluation` 为默认来源，查询没有 `async_task_id` 关联的 Evaluation 记录，返回 `source=persisted_business_evaluations`、`execution_backend=unassigned_or_legacy`、`production_queue_configured=false`。已关联异步任务的评估不再计入这组，避免双计。
- `task_source=async_task` 直接查询 AsyncTask 记录，返回 `source=persisted_async_tasks`、`execution_backend=celery`、`queue_infrastructure_available=true`、`real_evaluation_available=null`、`evaluation_worker_implementation=algorithm_harness`。基础设施标记只说明代码已存在，不代表 Redis/worker 已通过健康检查。
- 默认 100 条，`limit` 范围 1–1000，`offset` 范围 0–100000。响应返回 `status/items/total/counts/limit/offset/task_source`；`total` 与 `counts` 由所选来源和状态的全量记录聚合得到，`items` 只包含当前页。
- 两种来源都只返回任务 ID、所有者 ID、状态和经过范围校验的 `completed/total`；异步来源还返回白名单 `task_type`。非法状态或任务类型标记为 `other`，非法或不一致进度为 `null`。不返回原始进度消息、参数、错误详情或 Celery 任务 ID。
- `task_type` 白名单为 evaluation/experiment/benchmark/import；符合校验的 current/total 映射为 completed/total，缺失时返回 null。无论任务是否 completed，都不补造完成比例。AlgorithmHarness 实现标记只说明代码能力，不证明某次真实执行成功。
- 每次快照在单个只读事务中完成聚合和分页。监控不调用会同步 Celery 并提交状态的 `TaskManager.get_task`，也不轮询 Redis、恢复任务或重新调度。数据库不可读时返回 `status=unavailable`，`items/total/counts=null`，不将故障显示为空任务列表。

旧来源绑定当前应用的评估 engine；异步来源绑定当前应用启动时建立的任务 engine，与 `/tasks` 使用同一应用的任务会话工厂。并存应用不会因全局工厂后来被替换而读取其他应用的异步任务库。

任务状态跨服务重启持久化。已有评估服务在启动时按其恢复规则处理遗留记录；监控只读这些状态。异步任务的 completed 表示任务生命周期完成，不能据此推导 LLM 提供商的成功率；具体结果由结果接口查询。real_evaluation_available=null 与 execution_readiness=not_checked 表示本次监控没有验证模型、凭据和沙箱执行就绪。

```bash
curl http://localhost:8000/api/v1/health/sandbox \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl http://localhost:8000/api/v1/system/resources \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl 'http://localhost:8000/api/v1/system/tasks/running?task_source=async_task&limit=100' \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

CPU 每次采样 100ms，不使用首次无基线的瞬时零值；响应中的 `sample_seconds` 为 `0.1`。资源指标作用范围为 `api_host`，不返回本机路径。无法采集的组件标记 `unknown`，CPU 值为 `null`，其他缺失测量不填假零；健康故障返回通用安全说明。

Docker 预检可能启动一个短生命周期容器，由执行器负责资源限制和清理。一个 API 进程内使用锁及短缓存，避免并发请求重复启动探测容器；不同 API 进程各有自己的探测缓存。缓存响应通过 `cached` 标记是否复用，缓存到期后重新执行。预检结果不代表运行中全部容器的资源指标。

`file_storage` 只统计注册的活跃文件，明确排除未登记/暂存文件；磁盘测量覆盖整个上传文件系统。用户配额中的存储用量还包括等待清理的登记文件，两者有不同口径。

## 启用队列观测

```bash
export MONITOR_QUEUE_PROBES_ENABLED=true
export MONITOR_QUEUE_TIMEOUT_SECONDS=3
export MONITOR_QUEUE_CACHE_SECONDS=5
# API 与 worker 使用部署中相同的 CELERY_BROKER_URL。
# 升级后重启 API 和 worker，使 worker 加载 src.tasks.monitoring。
```

该命令遵循 [Celery 自定义 inspect 命令协议](https://docs.celeryq.dev/en/stable/userguide/workers.html#writing-your-own-remote-control-commands)，只返回版本号和三个计数，不请求 active/reserved/stats 的完整任务详情。探测在独立短生命周期进程中执行，连接信息经 stdin 传递，错误响应使用固定 reason，忽略第三方 stderr；连接、DNS、重试或回复卡住时终止并回收进程。

同类探测每个 API 进程最多一个在途请求，其他并发刷新得到 unknown/refresh_in_progress；缓存返回 cached=true 和 age_seconds，过期结果不会冒充新观测。停止 API 会终止在途探测。单次 worker 回复最多接受 128 个，达到截断条件时为 partial，聚合计数为 null。

禁用为 not_checked/disabled；连接失败为 unavailable/probe_failed；超时为 unknown/timeout；无 worker 回复为 unknown/no_replies，worker_count 和负载为 null。忙碌的 solo worker 也可能不及时回复，因此无回复不等于集群为空或离线。旧 worker 不支持命令、重复节点名称或非法计数均为 partial；仍可返回有效节点的计数，聚合负载为 null。重启旧 worker 可加载命令。失败结果也按 TTL 缓存，避免连续故障放大网络流量。

`system/status` 的 workers 复用其 health 内同一次观测，关闭缓存也不会重复广播。所有队列端点继续执行管理员 UUID 白名单校验，公开 `/health` 不访问 broker。

## 请求统计与完整性

- `GET /api/v1/metrics/api-stats?window_seconds=60`：统计窗口支持 1–86400 秒，提供请求量、HTTP 4xx/5xx 数与错误率、平均响应时间、P95 和每秒请求数。`endpoints` 按 HTTP 方法与路由模板分组提供同样统计，窗口不完整时各组也只展示 `retained_sample`。
- `GET /api/v1/metrics/performance`：API 请求统计、实际业务 SQL 查询统计、真实业务任务执行统计，以及尚待接入的 LLM 指标。
- `GET /api/v1/metrics/llm-stats`：管理员可查询共享认证数据库中成功采集的真实生成请求统计。`total_calls`、`successful_calls`、`failed_calls` 分别为已结束的 SDK 请求尝试数及其成功/失败数，`success_rate` 为成功数/总数（0–1），`avg_latency_ms` 为全部已记录尝试的平均耗时。无样本时计数为零、成功率和平均耗时为 `null`；`started_at` 为首次成功采集的完成时间（Unix 秒），此前为 `null`。`recorded_usage_hooks` 和 `key_verification_count` 仍分别展示使用登记与密钥连通验证计数，不计作生成调用。

LLM 采集位于 OpenAI、local、SiliconFlow 和 Anthropic 的实际 SDK 生成请求入口。每次重试分别计数；SDK 返回即为成功，生成的代码是否通过评测由评估指标表示。单调时钟耗时包含该次 SDK 请求的等待/超时，排除重试退避、响应本地解析和采集写入。缓存命中、模型列表、连接验证、沙箱预检和模拟任务均不计入。

API 和 worker 必须使用相同的 `AUTH_DATABASE_PATH`（跨容器需挂载同一 SQLite 文件），并配置有效的 `SECRET_KEY`、`ENCRYPTION_KEY`；未配置服务端认证的 CLI 仍能正常请求模型，但不采集到此数据库。`source=persisted_llm_attempts`、`scope=recorded_completed_attempts_shared_auth_database`、`collection_mode=best_effort` 明确该口径：统计跨进程和重启累计，仅覆盖成功落库的已完成尝试，不代表全部署精确总账。采集前历史、未共享该数据库的客户端、被强杀/尚未结束的请求及写入失败样本可能缺失；`status=ok` 表示统计可读取，不保证所有 worker 配置正确。聚合使用现有监控元数据表中的固定数值键，不保存 prompt、响应、模型名、URL、凭证或异常正文，不受请求/日志样本的保留期和行数裁剪。采集写入锁等待上限为 100ms，故障不会改变模型结果或增加模型重试。
- `GET /api/v1/metrics/llm-stats?window_seconds=60`：查询最近 60 秒；可选整数范围 1–86400，省略时保持上述累计口径。窗口按 SDK 尝试完成时间 `[window_start, window_end]`（Unix 秒，两端包含）过滤，返回 `total_calls`、`successful_calls`、`failed_calls`、`success_rate`（成功/全部，0–1）及 `avg_latency_ms`（全部尝试平均耗时，毫秒）。完整空窗口计数为零、成功率及平均耗时为 `null`；非法参数返回 400，权限仍限管理员。
- 窗口数据遵循 `MONITOR_RETENTION_SECONDS` 和 `MONITOR_MAX_ROWS`，仅保存完成时间、成功标志和耗时数值。`window_complete` 表示采集与保留覆盖；若窗口早于 `started_at` 或包含 `pruned_through` 之前被删除的记录，主指标为 `null`，`source=retained_sample`，可读取 `retained_sample` 的剩余样本。best-effort 仍可能遗漏采集失败或未配置客户端，不保证所有实际请求均已采集。升级前的累计值不会回填窗口；API 与 worker 需统一升级，历史累计不受清理影响。`recorded_usage_hooks` 和 `key_verification_count` 始终为独立累计值。
- `GET /api/v1/metrics/cache-stats`：自动读取实际 `LLMClient` 上报到共享监控数据库的缓存快照；无观测为 `not_configured`。worker 与 API 必须共享 `AUTH_DATABASE_PATH` 对应的存储。命中、未命中及节省调用数按保留的客户端实例生命周期快照汇总，重复上报覆盖；不是整个群集累计（`cluster_complete=false`）。整体命中率为 `sum(hits) / (sum(hits) + sum(misses))`，先汇总计数再相除，不对各 worker 的命中率取算术平均。例如两个 worker 分别为 9 hit / 1 miss 与 0 hit / 90 miss，整体为 9%，不是 45%。无缓存查询时命中率为 null；有查询且全部未命中时为 0；禁用缓存的模型调用不计入缓存查询分母。容量按同一主机的绝对缓存目录去重，取最新观测；包含磁盘上尚未删除的过期条目。`capacity_max_age_seconds` 表示最旧目录样本年龄，超过 300 秒返回 `partial` 且容量为 null。快照按监控保留期限和最多 min(MONITOR_MAX_ROWS,1024) 个实例限制。保留期限作用于快照更新时间，保留的每个快照包含该实例生命周期累计计数，并非该时间窗口内发生的请求数；重复上报覆盖该实例，实例快照到期或被数量上限淘汰后，其计数退出整体统计。成功采集的实例数由 `observed_instances` 表示，不等于 Celery worker 节点数，一个 worker 可创建多个客户端实例。采集发生在客户端创建、读取及写入后，不是周期性磁盘扫描；采集失败不影响生成。仍兼容可信进程显式绑定单一缓存实例，此时保留原 `bound_cache_instance`/进程内口径。

请求统计记录实际 HTTP 方法、匹配路由模板、状态码与响应耗时；不保存请求 body、query、Authorization 或原始资源路径。监控轮询本身也属于 API 请求。

`window_complete` 描述持久化记录对所选窗口的覆盖情况。刚启动、窗口超过保留期、行数/时间清理删掉窗口内记录，或窗口覆盖已知采集失败时，此值为 `false`，`source=retained_sample`；顶层 `request_count/errors/error_rate/avg_response_time_ms/p95_response_time_ms/requests_per_second` 返回 `null`。`retained_sample` 始终提供仍保留记录的样本统计，不应将其显示为完整流量或补齐成零。错误率以所有 HTTP 4xx/5xx 除以窗口请求数，空窗口为 `null`。

当窗口完整时，`source=persisted_requests`，上述顶层指标才提供窗口统计；空窗口的延迟仍为 `null`。`started_at/pruned_through/capture_gap_through/retention_seconds/max_rows` 可用于解释覆盖范围。

数据写入故障会记录通用警告并保留原 API 响应，同时标记采集缺口；数据库恢复后会持久化缺口水位。数据库完全不可写时，未落盘水位只能保留在当前进程中；若此时进程终止，后续重启不能恢复这段未落盘水位。当前存储不是确保每条事件入库的审计流水。

## 数据库查询统计

`GET /api/v1/metrics/performance` 的 `database_queries` 保留原有评估服务顶层统计（`engine_role=evaluation_service`），并通过 `sources` 列出当前 API 实例的实际采集来源。各来源分别提供 `query_count/successes/errors/error_rate/avg_latency_ms/p95_latency_ms/queries_per_second`，不混算不同来源的平均值或 p95。

- SQLAlchemy 来源：`evaluation`、`evaluation_results`、`experiment`、`benchmark`、`ab_test`、`cost`、`async_task`。分别绑定评估、结果读取、实验、基准、A/B、成本服务以及任务会话工厂的实际 engine；共享同一 engine 对象时合并 `roles`，执行只计一次。
- `auth_file` 来源：绑定当前 AuthStore 的原生 SQLite 连接，`roles=[auth,file,monitoring]`。认证、会话、限流、文件元数据、导入作业及使用同一 store 的监控读写均纳入；它们共用数据库，不能解释为独立的认证或文件查询计数。
- 每项包含固定 `source_id`、`roles`、`backend` 和 `process_id`。标识按绑定连接用途划分，同一数据库文件上的不同 engine 仍分别统计；不披露连接串、路径、SQL、参数或异常正文。

`coverage.scope=bound_sources_current_api_process`、`other_processes_included=false` 与 `storage=bounded_process_memory` 明确所有来源均为当前 API 进程的有界内存统计。SQLAlchemy 的 `scope=bound_business_engine_current_process`，SQLite 的 `scope=bound_auth_file_store_current_process`；不包含 Celery worker、其他 API 进程、独立 CLI/SQLite 连接或数据库服务端全局流量。重启后重新建立采集起点，API 启动前已完成的迁移不计入。健康检查、任务快照及监控自身使用这些连接的读写也会进入相应来源。

SQLAlchemy 查询数以 cursor 执行事件为单位；SQLite 覆盖连接及默认 cursor 的 `execute/executemany/executescript`，批量或脚本调用各计一次（脚本部分失败亦计失败一次），不是语句条数或返回行数。连接获取阶段错误不计作查询。SQLAlchemy 的 `latency_scope=cursor_execution_excludes_pool_wait_and_fetch`，SQLite 为 `sqlite_execution_call_excludes_connect_and_fetch`；均不代表事务完整耗时、结果处理时间或任务执行时间。

每个来源分别使用 `MONITOR_API_WINDOW_SECONDS`、`MONITOR_RETENTION_SECONDS` 与 `MONITOR_MAX_ROWS`。窗口不完整、样本淘汰或采集缺口时，`window_complete=false`、`source=retained_sample`，顶层统计为 `null`；`retained_sample` 仅展示实际保留样本。完整时沿用 `source=captured_business_queries`，具体数据源以 `source_id/roles` 识别。关闭监控后所有采集器停止，`collection_active=false`、`status=not_collecting`。SQLAlchemy 使用稳定事件转发，SQLite 弱注册采集器；采集故障不改变查询结果、原异常或事务回滚语义。

业务连接健康与查询样本完整性分别判断：没有完整统计窗口不等于数据库不可用。SQLite 路径已通过本地真实连接验证；PostgreSQL 的离线 SQL 和边界测试不能替代部署环境中实际 PostgreSQL 的连接与运行验证。

## 安全事件日志与下载

- `GET /api/v1/logs`：管理员查询保留的 API 生命周期与可信任务事件。
- `GET /api/v1/logs/tasks/{task_id}`：普通用户只查询自己的、仍存在且未删除的任务；其他用户资源与不存在资源均返回 404。
- `GET /api/v1/logs/download/{task_id}`：相同所有权校验后下载保留的匹配任务日志，固定附件名为 `task-logs.jsonl`；每行一个 JSON 事件，不接受服务器文件路径。

查询支持 `level/start/end/search/limit/offset`：

- 日志级别为 `DEBUG/INFO/WARNING/ERROR/CRITICAL`，不区分大小写。
- 起止时间为带时区的 ISO 8601 时间，不得早于 Unix epoch，且起点不能晚于终点。
- `search` 最多 200 字符，仅对脱敏后的消息做字面子串匹配。
- 分页默认 100 条，`limit` 范围 1–1000，`offset` 范围 0–100000；响应返回 `items/total/limit/offset`。
- 下载按同样过滤条件读取单次事务快照中的保留记录，不使用查询分页参数截取单页。匹配行数受 `MONITOR_MAX_ROWS` 影响，导出内容最多 32 MiB；输出写入服务持有的暂存句柄并流式发送。
- 下载响应头 `X-Retained-Log-Count`、`X-Exported-Log-Count`、`X-Log-Export-Truncated` 区分匹配总数、实际导出数及是否截断。遇到截断时缩小 `level/start/end/search` 筛选范围后再次下载；它不恢复已经清理的历史记录。暂存句柄在完成发送或客户端断开时关闭。

```bash
curl --get http://localhost:8000/api/v1/logs \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode 'start=2026-10-11T00:00:00+08:00' \
  --data-urlencode 'level=ERROR' --data-urlencode 'limit=100'
curl http://localhost:8000/api/v1/logs/download/your-task-id \
  -H "Authorization: Bearer $ACCESS_TOKEN" -o task-logs.jsonl
```

事件内容在入库前处理敏感字段和已知凭据，并限制消息、上下文大小与递归深度。未知对象不序列化，非有限数字不会直接写为 JSON 数值。下载带附件、`no-store` 和 `nosniff`，不公开全局 CLI 日志目录。删除任务后旧事件仍受所有权与任务存在检查保护，普通用户不能继续读取该任务日志。

## 现有配额查询

`GET /api/v1/quotas` 和 `/api/v1/quotas/usage` 只返回当前登录用户已有、实际执行的限额，不需要管理员身份：

- 文件存储用量与 `FILE_MAX_USER_BYTES`（默认 512 MiB）；包含等待物理清理的文件。
- 用户题库字节、条数与 `FILE_UPLOAD_MAX_BYTES/FILE_IMPORT_MAX_ITEMS`（默认 100 MiB / 10000 条）；题库与文件存储额度分别计算。
- 当前受保护请求窗口用量、`AUTH_PROTECTED_RATE_LIMIT`（默认每 60 秒 120 次）及窗口重置时间。配额查询自己也消耗一次受保护请求额度。
- 当前用户活跃导入数、共享 `FILE_MAX_ACTIVE_IMPORTS`（默认 8）、每进程导入并发（默认 2）和传输并发（默认 2）。
- `evaluation_concurrency`：`limit` 为实际准入配置 `MAX_CONCURRENT_EVALUATIONS_PER_USER`（默认 5），`used` 为当前用户业务库中 `pending/running` 评估任务数量，`remaining=max(limit-used,0)`。草稿、暂停、终态及其他类型任务不计入；历史用量超过新上限时保留真实 `used`，剩余为 0。两个配额别名均使用认证主体，不能通过 `user_id` 参数查询他人。查询只读、不轮询 Celery、不预留名额；状态变化以再次查询时的已提交记录为准，数据库错误不会返回虚假的零用量。

`daily_api_calls` / `monthly_api_calls` 按当前用户持久化统计真实 LLM **生成 SDK 尝试**：成功、失败及每次重试分别加一，缓存命中、模型列表、连接验证和无用户归属的 CLI 调用不计。归属来自服务端凭证解析，覆盖评估、实验、A/B 与 benchmark 的真实生成路径。

响应 `status=metered`、`used` 为整数（无记录为 0），`limit=null` 表示尚未配置日/月硬限额。`timezone=UTC`，按请求完成时间划分自然日与自然月，周期为 `[period_start, resets_at)`：每天 UTC 00:00、每月 1 日 UTC 00:00 切换（北京时间 08:00）。无需定时清零，旧周期保留，跨进程写入与重启后计数仍在，监控明细清理不影响聚合值。

`scope=owned_generation_sdk_attempts`，`collection_mode=best_effort_since_instrumentation`：只统计该功能启用后成功写入的尝试，旧全局数据无法按用户回填；持久化失败不改变原模型结果，但可能漏计。详细上传限额与清理规则见 [文件服务指南](api-files.md)。

## 离线配置目录与后续接入

管理员可查询：

- `GET /api/v1/config/strategies`：复用 `AlgorithmHarness.STRATEGY_MAP` 和 `StrategyConfig` 的默认资源参数。
- `GET /api/v1/config/providers`：静态支持的提供商与固定示例配置中的模型名称，`scope=offline_example_catalog`。不访问远端模型列表，不验证当前可用性，不返回密钥或自定义 URL；CLI 提供商能力列表也不会扩大认证密钥接口的提供商白名单。
- `GET /api/v1/config/sandbox`：受控 Docker 镜像、执行超时、内存、进程、输出和允许导入配置，不返回主机目录或环境变量。

#149 的异步任务执行与产品 HTTP 入队已合入。API 启动保留现有任务工厂和服务恢复策略，关闭时清理探测子进程及查询采集器。Redis/worker 探测须由部署者启用，并重启 worker 以加载新的只读 inspect 命令。探测不会调用 TaskManager.get_task、创建业务任务、撤销或恢复任务，也不会直接更新任务数据库。

真实 worker 可用可信任务所有者调用 `app.state.monitor.record_task_event(event, user_id)`。入口会校验登记的任务归属和删除状态；HTTP 不开放指定所有者、写日志或绑定缓存的接口。实际 LLM 缓存通过客户端自动上报共享快照，无需将 worker 对象直接绑定到 API 进程；`app.state.monitor.cache` 仅保留可信进程的单实例兼容入口。

Redis 连通性和回复 worker 的数值负载已接入。broker 等待队列长度、真实任务执行时长/成功率、LLM 请求时延、各容器 CPU/内存及新日/月配额仍需后续采集。数据库健康和绑定 engine 的查询时延已接入；健康探测不构成真实模型调用成功证明。#157 保持开放。

## Docker 沙箱容器资源

```bash
export MONITOR_CONTAINER_PROBES_ENABLED=true
export MONITOR_CONTAINER_TIMEOUT_SECONDS=3
export MONITOR_CONTAINER_CACHE_SECONDS=5
export MONITOR_CONTAINER_MAX_ITEMS=32
```

默认关闭；仅管理员 `system/status` 的 `containers` 字段按需采样，公开 `/health` 和 401/403 路径不访问 Docker。读取当前 API 进程 Docker CLI 配置所指向的 context，不代表所有 worker 的 Docker daemon。需部署者将 API 指向实际需要观测的 daemon；无需为只读观测启动业务任务。

新版本 SandboxExecutor 创建容器时增加 `io.llm-algorithm-harness.sandbox=v1`。采样固定执行带该 label 过滤的 `docker ps`，再对选中的完整 ID 执行 `docker stats --no-stream`，不调用 run/stop/rm/exec/inspect。标签只是观测选择器，不是认证或用户归属证明；旧版未带标签的容器和其他无标签容器不计入范围。

响应只包含稳定摘要 `container_id`、CPU 百分比、内存显示值转换的字节/限额/百分比和 PIDs；不返回容器名称、原始 ID、镜像、命令、挂载、环境或 Docker 错误。数值来源为 `docker_cli_rounded_stats`，不是精确字节计数或 API 主机资源。[Docker stats 官方说明](https://docs.docker.com/reference/cli/docker/container/stats/) 中 Linux CLI 内存会扣除部分缓存，PIDs 包含线程；Windows daemon 部分列不提供，返回 null/partial，不能据此判定整个 daemon 不可用。Windows 主机连接 Linux daemon 时以 daemon 返回字段为准。

`listed_count` 是成功枚举时的标签范围数量，`sampled_count` 是实际选取的数量；默认32，配置范围1–64。超过样本上限为 partial/sample_limit、truncated=true，不生成全局 CPU/内存汇总。容器在 ps 与 stats 之间退出或字段不可用时，该行 unknown/partial，缺测为 null；stats 非零退出仍保留成功枚举和合法数值，总体 partial/stats_failed，不把正常 --rm 完成误报为整个 Docker 不可用；仅成功枚举为空才返回真实0和空数组。`snapshot_atomic=false`、`cluster_complete=false`，不能从一张快照证明整个集群为空或任务已终止。

ps 与 stats 分享0.5–10秒命令预算，各自接受的合计输出上限64KiB，超限即终止命令进程树并返回固定 output_limit；错误、超时和无 Docker 时不泄露原始输出。复用既有进程工具，异常时两个 pipe join 各最多5秒，终止清理可能增加有界余量。服务关闭标记 closed、拒绝新采样，并最多等待当前预算加12秒清理余量；不会停止被观测的容器。

每 API 进程最多一个采样，缓存0–300秒，失败也缓存；cached/age_seconds 描述完成后的缓存年龄。缓存过期且另一个采样在途时返回 unknown/refresh_in_progress，不把旧成功值当成新观测。缓存独立于 worker/Redis 观测。

本功能仅完成 #157 的容器资源观测；LLM 生成性能和新增配额仍需后续实现。跨 worker 缓存计数及整体命中率已通过共享快照提供，范围和公式见上文缓存统计接口。

### 实际任务执行统计

`GET /api/v1/metrics/performance` 的 `tasks` 从业务数据库持久化的 AsyncTask 聚合 evaluation、experiment、benchmark、import 四类任务；`evaluations` 使用相同口径但仅包含 evaluation。接口沿用管理员权限，查询不轮询 Celery、不读取结果正文。`scope=retained_business_tasks_all_time` 表示当前数据库保留记录的累计统计，不使用 API 请求窗口，也不包含旧的无 AsyncTask 评估。

`avg_execution_time_seconds` 是 completed/failed 且开始、结束时间均存在且顺序有效的任务的平均墙钟秒数，`duration_sample_count` 给出耗时样本数。耗时从首次执行开始到最终结束，排除首次排队等待，包含暂停及重试间隔，不表示 CPU 活跃执行时间。重复通知保留已有时间，失败后重新执行保留首次开始并清空旧结束时间。

`completed`、`failed` 只计已记录开始时间的相应终态任务；`success_rate=completed/(completed+failed)`（0–1）表示任务正常完成率，不代表算法答题准确率。取消、等待、运行、暂停和未开始的发布失败不计入；时间缺失或逆序的已开始终态任务仍计入成功率，但不进入耗时样本。无样本时相应指标为 null，数据库不可用时 status=unavailable、计数及指标均为 null，不返回底层异常。


## 真实队列长度

启用 `MONITOR_QUEUE_PROBES_ENABLED=true` 后，`health/redis` 的 `broker_queue` 返回 `status/reason/waiting/queues`，`queues` 为 `{name, waiting}` 列表。队列来自实际 Celery `task_queues`（当前为 default、evaluations），每队列等待数覆盖所有 `priority_steps` 分桶，遵循 `sep` 和 `global_keyprefix`。只执行 PING 和 LLEN，不扫描键、不读取消息、不消费任务；没有配置的队列及 unacked 不计入。

`system/status` 的 `queue_metrics` 分别展示：

- `broker_queue.waiting`：Redis 中尚未交给 worker 的消息总数，附各队列计数和缓存年龄。
- `database_pending.count`：持久化 AsyncTask 的 pending 记录数，保留数据库来源和状态。
- `worker_reserved.count`：回复 worker 已接收且尚未执行的数量，`cluster_complete=false`，附缓存年龄。

三项观测独立且非原子，不相加、不互相推算。Redis 正常空队列返回 0；关闭探测、配置非法、超时、连接/LLEN 失败或协议异常时等待数为 null。PING 状态与 `broker_queue.status` 独立：PING 成功不能证明 LLEN 权限或队列观测成功。现有 queued 任务列表仍只查询数据库 pending。
