# API 系统监控基础能力（#157）

本次实现可独立运行的 API 监控基础：管理员授权、本机资源和 Docker 预检、持久化请求统计、安全事件日志、离线配置目录，以及当前用户已有配额的查询。#157 仍需后续接入 #149 的真实队列、worker 和 LLM 指标，以及 #151 的业务数据库。

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

请求和日志保存在现有认证 SQLite 的 `api_monitor_*` 表中，复用 `AUTH_DATABASE_PATH`，没有另行创建业务数据库。统计起点与清理水位持久化，同机多进程共享同一数据库时共享这些记录；本机资源、API 模拟任务和缓存实例仍有各自作用范围。

## 健康与资源端点

公开的 `GET /api/v1/health` 仅表示 API 存活，响应包含 `scope=api_liveness_only`。它不执行 Docker 探测，也不代表队列或业务数据库可用。

以下端点全部需要管理员身份，成功响应使用现有 `success/data/message` 包装：

- `GET /api/v1/system/health`：当前基础服务状态。尚未配置 #149/#151 时返回 `status=partial`；已执行的 SQLite 或 Docker 检查失败时为 `degraded`。默认不探测 Docker；传 `include_sandbox=true` 可加入预检。
- `GET /api/v1/health/database`：对实际认证/文件 SQLite 执行 `SELECT 1`，并验证所需表可查询。`business_database` 明确返回 `not_configured`、`dependency_issue=151`。
- `GET /api/v1/health/redis`：返回 `not_configured`、`dependency_issue=149`。
- `GET /api/v1/health/workers` 与 `/api/v1/system/workers`：返回 `not_configured`、`dependency_issue=149`。
- `GET /api/v1/health/sandbox`：复用实际 `SandboxExecutor.health_check()` 执行 Docker 预检，失败为 `unavailable`。只使用 Docker；不可用时不回退 host，不返回异常中的主机路径或凭据。
- `GET /api/v1/system/resources`：CPU、内存、上传目录所在文件系统的磁盘用量，以及已登记且未标记删除的文件数量/字节。
- `GET /api/v1/system/status`：当前 API 进程运行时间、模拟任务计数、基础健康与本机资源。容器级资源采集返回 `not_configured`。
- `GET /api/v1/system/tasks/running` 和 `/api/v1/system/tasks/queued`：当前 API 进程的模拟器任务快照，来源为 `in_process_evaluation_simulator`；不能当成集群 worker 或 Redis 队列状态。

```bash
curl http://localhost:8000/api/v1/health/sandbox \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl http://localhost:8000/api/v1/system/resources \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

CPU 每次采样 100ms，不使用首次无基线的瞬时零值；响应中的 `sample_seconds` 为 `0.1`。资源指标作用范围为 `api_host`，不返回本机路径。无法采集的组件标记 `unknown`，CPU 值为 `null`，其他缺失测量不填假零；健康故障返回通用安全说明。

Docker 预检可能启动一个短生命周期容器，由执行器负责资源限制和清理。一个 API 进程内使用锁及短缓存，避免并发请求重复启动探测容器；不同 API 进程各有自己的探测缓存。缓存响应通过 `cached` 标记是否复用，缓存到期后重新执行。预检结果不代表运行中全部容器的资源指标。

`file_storage` 只统计注册的活跃文件，明确排除未登记/暂存文件；磁盘测量覆盖整个上传文件系统。用户配额中的存储用量还包括等待清理的登记文件，两者有不同口径。

## 请求统计与完整性

- `GET /api/v1/metrics/api-stats?window_seconds=60`：统计窗口支持 1–86400 秒，提供请求量、HTTP 4xx/5xx 数与错误率、平均响应时间、P95 和每秒请求数。`endpoints` 按 HTTP 方法与路由模板分组提供同样统计，窗口不完整时各组也只展示 `retained_sample`。
- `GET /api/v1/metrics/performance`：API 请求统计与尚待接入的评估、业务数据库查询、LLM 指标。
- `GET /api/v1/metrics/llm-stats`：真实生成调用数、成功率、延迟目前为 `not_configured`，数值为 `null`。已有 `recorded_usage_hooks` 和 `key_verification_count` 分别展示使用登记与密钥连通验证计数，不计作真实生成调用总量或成功率。
- `GET /api/v1/metrics/cache-stats`：默认 `not_configured`。仅在可信 worker 显式绑定实际 `LLMResponseCache` 后展示其白名单统计；命中、未命中等计数为实例创建以来的进程内计数，不代表所有 worker 的累计值。

请求统计记录实际 HTTP 方法、匹配路由模板、状态码与响应耗时；不保存请求 body、query、Authorization 或原始资源路径。监控轮询本身也属于 API 请求。

`window_complete` 描述持久化记录对所选窗口的覆盖情况。刚启动、窗口超过保留期、行数/时间清理删掉窗口内记录，或窗口覆盖已知采集失败时，此值为 `false`，`source=retained_sample`；顶层 `request_count/errors/error_rate/avg_response_time_ms/p95_response_time_ms/requests_per_second` 返回 `null`。`retained_sample` 始终提供仍保留记录的样本统计，不应将其显示为完整流量或补齐成零。错误率以所有 HTTP 4xx/5xx 除以窗口请求数，空窗口为 `null`。

当窗口完整时，`source=persisted_requests`，上述顶层指标才提供窗口统计；空窗口的延迟仍为 `null`。`started_at/pruned_through/capture_gap_through/retention_seconds/max_rows` 可用于解释覆盖范围。

数据写入故障会记录通用警告并保留原 API 响应，同时标记采集缺口；数据库恢复后会持久化缺口水位。数据库完全不可写时，未落盘水位只能保留在当前进程中；若此时进程终止，后续重启不能恢复这段未落盘水位。当前存储不是确保每条事件入库的审计流水。

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

#149 worker 可用可信任务所有者调用 `app.state.monitor.record_task_event(event, user_id)`。入口会校验登记的任务归属和删除状态；HTTP 不开放指定所有者、写日志或绑定缓存的接口。真实 worker 可将实际 LLM 客户端的缓存实例绑定到 `app.state.monitor.cache`，仍需明确其单实例口径。

队列长度、活跃 worker、任务执行时长/成功率、LLM 请求数/延迟，以及各容器 CPU/内存，需后续采集接入；#151 接入后还需业务数据库连通性与查询延迟采集。当前任务取消继续使用已有所有者权限的评估取消接口，没有增加管理员跨用户强制终止接口。完整 RBAC、远端日志平台和告警通知也未在本次基础实现中提供。
