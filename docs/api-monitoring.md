# API 系统监控基础能力（#157）

本次实现 API 监控基础：管理员授权、本机资源和 Docker 预检、持久化请求统计、安全事件日志、离线配置目录，以及当前用户已有配额的查询。#151 已接入业务数据库；#179 已合并 Celery/Redis 与异步任务管理基础，#180 已增加实验、导入和基准的 Celery 执行入口。本次监控分别读取旧评估和异步任务的持久化状态、检查数据库连接与 schema，并采集实际业务 SQL 查询统计。异步评估 worker 仍返回模拟结果；#149 保持开放，真实评估、使用计量与 worker 监控指标仍需接入。

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
- `MONITOR_SANDBOX_IMAGE`：`python:3.11-slim`；仅接受受控 Docker 镜像引用。
- `MONITOR_SANDBOX_TIMEOUT_SECONDS`：5，范围 1–30；Docker 预检中的单个用例执行超时。

请求和日志保存在现有认证 SQLite 的 `api_monitor_*` 表中，复用 `AUTH_DATABASE_PATH`。统计起点与清理水位持久化，同机多进程共享同一数据库时共享这些记录。评估任务保存在 #151 的业务数据库，由 `DATABASE_URL` 配置，默认是 `data/business/business.sqlite3`；它与认证和文件元数据 SQLite 独立。业务 SQL 指标、本机资源及缓存实例各有自己的作用范围，详见下文。

## 健康与资源端点

公开的 `GET /api/v1/health` 仅表示 API 存活，响应包含 `scope=api_liveness_only`。它不执行 Docker 探测，也不代表队列或业务数据库可用。

以下端点全部需要管理员身份，成功响应使用现有 `success/data/message` 包装：

- `GET /api/v1/system/health`：当前基础服务状态。队列基础已存在，但 Redis/worker 尚未执行联网检查、真实执行指标尚未接入，返回 `status=partial`，`pending_issues=[149]`；已执行的数据库或 Docker 检查失败时为 `degraded`。默认不探测 Docker；传 `include_sandbox=true` 可加入预检。
- `GET /api/v1/health/database`：对实际认证/文件 SQLite 执行 `SELECT 1`，并验证所需表可查询；`business_database` 使用已绑定的评估服务 engine 检查实际连接、业务表与 Alembic revision，返回 `status/backend/required_tables/migration/read_only/latency_ms`。迁移检查按仓库 Alembic 元数据的 heads 比对数据库当前 heads，成功时通过 `migration.status/revisions/expected_heads` 说明版本一致；不一致时标记故障，不回显数据库中的任意版本文本。探测只读，不运行迁移、不创建评估服务，也不修改任务状态；不返回连接串、主机路径或凭据。任一已配置数据库检查失败时，总体状态为 `unavailable`。
- `GET /api/v1/health/redis`：队列基础已合并，本轮不进行 Redis 网络探测，返回 `status=not_checked`、`infrastructure_available=true`、`dependency_issue=149`。基础设施标记只说明代码已存在，不证明 Redis 已启动或可达。
- `GET /api/v1/health/workers` 与 `/api/v1/system/workers`：Celery 基础已合并，本轮不轮询 worker，返回 `status=not_checked`、`infrastructure_available=true`、`dependency_issue=149`，以及 `evaluation_worker_implementation=mock`、`real_evaluation_available=false`；它不证明已有活跃 worker 或生产评估可用。
- `GET /api/v1/health/sandbox`：复用实际 `SandboxExecutor.health_check()` 执行 Docker 预检，失败为 `unavailable`。只使用 Docker；不可用时不回退 host，不返回异常中的主机路径或凭据。
- `GET /api/v1/system/resources`：CPU、内存、上传目录所在文件系统的磁盘用量，以及已登记且未标记删除的文件数量/字节。
- `GET /api/v1/system/status`：当前 API 进程运行时间、旧评估与异步任务各自的全量状态计数、基础健康与本机资源。旧来源保留 `task_counts/task_count/task_status/task_source`，来源值为 `persisted_business_evaluations`；异步来源新增 `async_task_counts/async_task_count/async_task_status/async_task_source`，来源值为 `persisted_async_tasks`。两组分别读取，不受分页限制，不提供相加后的全局原子快照；一组故障时只将该组计数标记为 `null`，状态为 `unavailable`。响应另含 `evaluation_worker_implementation=mock`、`real_evaluation_available=false`。容器级资源采集返回 `not_configured`。
- `GET /api/v1/system/tasks/running` 和 `/api/v1/system/tasks/queued`：分别查询所选持久化来源中 `running` 和 `pending` 状态的任务；`queued` 只表示数据库记录的 `pending` 状态，不能当成 Redis 队列长度。

任务查询支持 `task_source/limit/offset`：

- `task_source=legacy_evaluation` 为默认来源，查询没有 `async_task_id` 关联的 Evaluation 记录，返回 `source=persisted_business_evaluations`、`execution_backend=in_process_simulator`、`production_queue_configured=false`。已关联异步任务的评估不再计入这组，避免双计。
- `task_source=async_task` 直接查询 AsyncTask 记录，返回 `source=persisted_async_tasks`、`execution_backend=celery`、`queue_infrastructure_available=true`、`real_evaluation_available=false`、`evaluation_worker_implementation=mock`。基础设施标记只说明代码已存在，不代表 Redis/worker 已通过健康检查。
- 默认 100 条，`limit` 范围 1–1000，`offset` 范围 0–100000。响应返回 `status/items/total/counts/limit/offset/task_source`；`total` 与 `counts` 由所选来源和状态的全量记录聚合得到，`items` 只包含当前页。
- 两种来源都只返回任务 ID、所有者 ID、状态和经过范围校验的 `completed/total`；异步来源还返回白名单 `task_type`。非法状态或任务类型标记为 `other`，非法或不一致进度为 `null`。不返回原始进度消息、参数、错误详情或 Celery 任务 ID。
- `task_type` 白名单为 `evaluation/experiment/benchmark/import`。#180 的导入入口会写入数值 `current/total`，符合校验时映射为 `completed/total`；实验和基准入口当前不写入数值进度，缺失时返回 `null`。`evaluation_worker_implementation=mock` 只描述评估 worker，不表示全部任务类型都是模拟器。
- 每次快照在单个只读事务中完成聚合和分页。监控不调用会同步 Celery 并提交状态的 `TaskManager.get_task`，也不轮询 Redis、恢复任务或重新调度。数据库不可读时返回 `status=unavailable`，`items/total/counts=null`，不将故障显示为空任务列表。

旧来源绑定当前应用的评估 engine；异步来源绑定当前应用启动时建立的任务 engine，与 `/tasks` 使用同一应用的任务会话工厂。并存应用不会因全局工厂后来被替换而读取其他应用的异步任务库。

任务状态跨服务重启持久化。已有评估服务在启动时按其恢复规则处理遗留记录；监控只读这些状态。异步评估任务的 `completed` 说明当前模拟评估 worker 生命周期已完成，不能据此推断真实 LLM 评估成功率；其他任务类型的完成状态按各自业务入口记录。

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

## 请求统计与完整性

- `GET /api/v1/metrics/api-stats?window_seconds=60`：统计窗口支持 1–86400 秒，提供请求量、HTTP 4xx/5xx 数与错误率、平均响应时间、P95 和每秒请求数。`endpoints` 按 HTTP 方法与路由模板分组提供同样统计，窗口不完整时各组也只展示 `retained_sample`。
- `GET /api/v1/metrics/performance`：API 请求统计、实际业务 SQL 查询统计，以及尚待接入的真实评估与 LLM 指标。
- `GET /api/v1/metrics/llm-stats`：真实生成调用数、成功率、延迟目前为 `not_configured`，数值为 `null`。已有 `recorded_usage_hooks` 和 `key_verification_count` 分别展示使用登记与密钥连通验证计数，不计作真实生成调用总量或成功率。
- `GET /api/v1/metrics/cache-stats`：默认 `not_configured`。仅在可信 worker 显式绑定实际 `LLMResponseCache` 后展示其白名单统计；命中、未命中等计数为实例创建以来的进程内计数，不代表所有 worker 的累计值。

请求统计记录实际 HTTP 方法、匹配路由模板、状态码与响应耗时；不保存请求 body、query、Authorization 或原始资源路径。监控轮询本身也属于 API 请求。

`window_complete` 描述持久化记录对所选窗口的覆盖情况。刚启动、窗口超过保留期、行数/时间清理删掉窗口内记录，或窗口覆盖已知采集失败时，此值为 `false`，`source=retained_sample`；顶层 `request_count/errors/error_rate/avg_response_time_ms/p95_response_time_ms/requests_per_second` 返回 `null`。`retained_sample` 始终提供仍保留记录的样本统计，不应将其显示为完整流量或补齐成零。错误率以所有 HTTP 4xx/5xx 除以窗口请求数，空窗口为 `null`。

当窗口完整时，`source=persisted_requests`，上述顶层指标才提供窗口统计；空窗口的延迟仍为 `null`。`started_at/pruned_through/capture_gap_through/retention_seconds/max_rows` 可用于解释覆盖范围。

数据写入故障会记录通用警告并保留原 API 响应，同时标记采集缺口；数据库恢复后会持久化缺口水位。数据库完全不可写时，未落盘水位只能保留在当前进程中；若此时进程终止，后续重启不能恢复这段未落盘水位。当前存储不是确保每条事件入库的审计流水。

## 业务 SQL 查询统计

`GET /api/v1/metrics/performance` 的 `database_queries` 从运行中的评估服务 SQLAlchemy engine 采集真实 cursor 执行完成与失败事件，`engine_role=evaluation_service`，提供 `query_count/successes/errors/error_rate/avg_latency_ms/p95_latency_ms/queries_per_second`。实验、基准、A/B 服务及异步任务会话工厂的独立 engine 尚未纳入这个口径；异步任务查询不会全部出现在此计数中。查询数以 cursor 执行事件为单位，不是返回行数；连接获取阶段的错误不计作已执行查询。它不保存 SQL 文本、绑定参数、连接 URL、异常详情或用户数据。绑定评估 engine 上的数据库健康检查和旧任务监控查询本身也会进入这个采集口径。

`scope=bound_business_engine_current_process` 表示单 engine、单 API 进程；不包含认证/文件 SQLite、其他进程或数据库服务端的全局查询。每 engine 在启动时安装一个稳定转发监听，弱注册采集器；监控关闭后停止采集并解除采集器引用，此后 `collection_active=false`、`status=not_collecting`。空转发器随 engine 生命周期回收，关闭时不并发修改 SQLAlchemy 事件队列，以保护仍在执行的业务查询。统计仅保存在当前进程内，重启后重新建立采集起点，API 启动前已经完成的迁移和任务恢复查询不计入。

统计使用 `MONITOR_API_WINDOW_SECONDS` 指定的窗口，保留时间和行数分别受 `MONITOR_RETENTION_SECONDS` 与 `MONITOR_MAX_ROWS` 限制。窗口尚未被完整采集、记录被淘汰或采集发生缺口时，`window_complete=false`、`source=retained_sample`，顶层统计为 `null`，`retained_sample` 仅展示实际保留样本；完整时 `source=captured_business_queries`。`started_at/pruned_through/capture_gap_through` 说明采集起点和覆盖缺口。`latency_scope=cursor_execution_excludes_pool_wait_and_fetch` 明确查询延迟衡量 cursor 执行阶段，不表示连接等待、事务完整耗时、结果处理时间或真实任务执行时长。

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

每日/每月 LLM API 调用额度为 `not_configured`，`limit/used` 为 `null`，需在真实请求计量接入后补齐。详细上传限额与清理规则见 [文件服务指南](api-files.md)。

## 离线配置目录与后续接入

管理员可查询：

- `GET /api/v1/config/strategies`：复用 `AlgorithmHarness.STRATEGY_MAP` 和 `StrategyConfig` 的默认资源参数。
- `GET /api/v1/config/providers`：静态支持的提供商与固定示例配置中的模型名称，`scope=offline_example_catalog`。不访问远端模型列表，不验证当前可用性，不返回密钥或自定义 URL；CLI 提供商能力列表也不会扩大认证密钥接口的提供商白名单。
- `GET /api/v1/config/sandbox`：受控 Docker 镜像、执行超时、内存、进程、输出和允许导入配置，不返回主机目录或环境变量。

#179 已提供 Celery/Redis、AsyncTask 和任务控制基础，#180 已合入实验、导入和基准三类 Celery 任务实现；本轮保留现有任务路由、应用启动时绑定的任务会话工厂和关闭时的 engine 清理。这三类 Celery 入口的端到端执行与真实 LLM 指标仍未接通或验证。新增入口不等于 HTTP 请求已自动改为队列：`/evaluations` 仍保留旧评估流程，文件导入仍使用 BackgroundTasks，实验和基准 HTTP 服务仍使用进程内后台线程。异步评估实现也仍使用返回 `mock=true` 的占位 worker；#149 尚未全部完成。

真实 worker 可用可信任务所有者调用 `app.state.monitor.record_task_event(event, user_id)`。入口会校验登记的任务归属和删除状态；HTTP 不开放指定所有者、写日志或绑定缓存的接口。现有异步 worker 尚未绑定此入口或实际 LLM 缓存；后续可将实际 LLM 客户端的缓存实例绑定到 `app.state.monitor.cache`，仍需明确其单实例口径。

Redis 实际连通性、队列长度、活跃 worker、真实任务执行时长/成功率、LLM 请求数/延迟，以及各容器 CPU/内存，需后续探测与采集接入。业务数据库连通性、schema 与绑定 engine 的实际查询延迟现已接入；不会把持久化的模拟任务结果或模拟成本计作真实 worker/LLM 指标。取消继续使用已有所有者权限的评估或任务控制接口，没有增加管理员跨用户强制终止接口。完整 RBAC、远端日志平台和告警通知也未在本次基础实现中提供。#157 保持开放。
