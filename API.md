# LLM Algorithm Harness REST API

API 基础地址为 `http://localhost:8000/api/v1`，当前 HTTP 契约版本为 `1.0.0`，应用发布版本为 `0.1.0`。
采用 URL 主版本，不使用 Header 版本协商；演进与兼容性检查规则见 [API 版本管理](docs/api-versioning.md)。
所有已注册 HTTP 端点的参数、约束、认证要求、限流说明、请求/响应示例及 curl 命令，均从服务的 OpenAPI 文档读取：

- [Swagger UI](http://localhost:8000/docs)：展开端点后点击 **Try it out** 发起请求。
- [ReDoc](http://localhost:8000/redoc)：阅读端点、模型和 Shell 示例。
- [OpenAPI JSON](http://localhost:8000/openapi.json)：导入客户端或保存用于离线阅读。

文档跟随当前路由和 Pydantic 模型自动生成；`api/documentation.py` 补充业务语义和示例。
`/docs`、`/redoc`、`/openapi.json` 无需认证。Swagger UI 和 ReDoc 默认从 CDN 加载界面脚本，
浏览器需能访问这些资源；JSON 规范本身不依赖 CDN。

## 启动和保存规范

从仓库根目录安装依赖并生成本地开发密钥（生产环境按[认证指南](docs/api-authentication.md)管理密钥）：

```bash
python3 -m pip install -e '.[dev]'
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
./run_api.sh --host localhost --port 8000
```

在另一个终端保存最新 OpenAPI：

```bash
curl --fail http://localhost:8000/openapi.json --output openapi.json
```

生成规范不需要运行数据库、Redis 或 LLM 请求。正常启动服务仍需要有效签名/加密密钥，
并会初始化本地数据存储。执行异步评估、实验、基准或导入任务还需要配置 Redis 和 Celery worker，
参见[异步任务部署](docs/deployment/async-tasks.md)。

## 认证和访问权限

- 公开端点：`GET /health`，`POST /auth/register`、`/auth/login`、`/auth/refresh`。
- 其他 HTTP 端点要求 `Authorization: Bearer <access_token>`。Swagger UI 右上角 **Authorize** 中只填访问令牌，不要填提供商 API Key。
- 评估、异步任务、实验、基准、A/B 测试、文件及日志按所有者隔离。不可访问的资源通常返回 404，避免泄露其他用户资源是否存在。
- 系统监控、依赖健康、全局指标/日志及服务器配置目录要求管理员身份。
  管理员由环境变量 `MONITOR_ADMIN_USER_IDS` 配置为用户 UUID 的 JSON 数组，不能通过注册请求或 token 自行声明。
- `/users/me` 返回服务器解析的 `role`。`/auth/refresh` 轮换刷新令牌，旧刷新令牌不能再次使用。
  `/auth/logout` 撤销当前会话；`/users/me/password` 修改密码后撤销所有会话。
- LLM 提供商 Key 先通过 `/api-keys` 加密保存，再用返回的 `id` 作为 `api_key_id`。响应只包含 `masked_preview` 等元数据。

[认证完整说明](docs/api-authentication.md)包含密钥配置、令牌生命周期和密码要求。

## 速率限制与容量

以下为默认值，部署可通过同名环境变量调整；每个端点的交互文档也显示适用限制：

- 注册、登录、刷新按客户端 IP 共享 `AUTH_RATE_LIMIT=10` 次 / `AUTH_RATE_WINDOW_SECONDS=60` 秒。
- 受保护接口按用户共享 `AUTH_PROTECTED_RATE_LIMIT=120` 次 / 同一认证窗口。
- 三个上传端点额外按 IP 和用户分别应用 `FILE_UPLOAD_RATE_LIMIT=10` 次 / 同一认证窗口。
- 文件上传、原始文件下载、题库导出，以及 `/results/` 下的路径还受每个 API 进程
  `FILE_MAX_CONCURRENT_TRANSFERS=2` 的传输并发容量限制。它和请求次数限制是两个独立限制。
- 限流或传输容量不足返回 `429/RATE_LIMIT_EXCEEDED`，按响应 `Retry-After` 秒数等待后重试。
- 公开 `/health` 没有应用级请求限流；WebSocket 不经过上述 HTTP 请求次数限流。
- 上传默认单文件最大 `FILE_UPLOAD_MAX_BYTES=104857600`（100 MiB），配置文件还受
  `FILE_CONFIG_MAX_BYTES=1048576`（1 MiB）限制；用户存储默认 512 MiB。
  导入题目数、导入并发和活跃任务数另有容量限制，参见[文件服务](docs/api-files.md)。
- `/quotas` 和 `/quotas/usage` 查询自己的实际生效额度；未配置的日/月 API 配额显示 null。

## 从注册到评估结果

示例凭证均为虚构值。先运行注册，再登录；已经注册时可直接登录。
所有资源 ID 必须从自己的前序响应中获取。示例题目须已导入业务题库，模型须受自己的提供商密钥支持。
以下操作会创建账户、保存密钥或创建/执行评估，按需在本地开发服务使用。

```bash
export API_URL=http://localhost:8000/api/v1
curl --fail-with-body -X POST "$API_URL/auth/register" \
  -H 'Content-Type: application/json' \
  --data '{"username":"demo","email":"demo@example.com","password":"Example-password-123!"}'

curl --fail-with-body -X POST "$API_URL/auth/login" \
  -H 'Content-Type: application/json' \
  --data '{"username":"demo","password":"Example-password-123!"}'

# 从登录响应 data.access_token 复制值。
export ACCESS_TOKEN='REPLACE_WITH_ACCESS_TOKEN'

curl --fail-with-body -X POST "$API_URL/api-keys" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"provider":"openai","key_name":"Demo key","api_key":"REPLACE_WITH_PROVIDER_KEY"}'

# 用上一步 data.id 替换 api_key_id，使用自己的题目 ID。
curl --fail-with-body -X POST "$API_URL/evaluations" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"api_key_id":"REPLACE_WITH_KEY_ID","model":"gpt-4o-mini","problem_ids":["two-sum"],"strategy_names":["vanilla"],"budget_cap_usd":1.0}'

# 创建返回 201/pending；启动才提交后台运行。
export EVALUATION_ID='REPLACE_WITH_EVALUATION_ID'
curl --fail-with-body -X POST "$API_URL/evaluations/$EVALUATION_ID/start" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl --fail-with-body "$API_URL/evaluations/$EVALUATION_ID/progress" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl --fail-with-body "$API_URL/results/$EVALUATION_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 报告是附件，不是 ApiResponse；不要把 HTTP 头写入文件内容。
curl --fail-with-body "$API_URL/reports/csv/$EVALUATION_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" --output results.csv
```

`202` 表示后台操作已受理，不代表执行完成。轮询对应的评估、异步任务、实验或基准运行详情。
预算、依赖和执行失败可能在后续状态中出现，启动请求的成功响应不保证评估成功。

实验/基准请求的 `dataset_path` 在服务器 `DATA_ROOT` 内解析（默认 `data`）；
例如磁盘上的 `data/problems.json` 在请求中写 `problems.json`，不能使用客户端磁盘路径。
完整请求参数请展开对应操作的 **Schema**；所有 JSON 请求示例均使用当前请求模型。

## 上传、导入与导出

上传请求为 `multipart/form-data`，每次恰好一个 `file` 字段；由 curl 自动设置包含 boundary 的 Content-Type。

```bash
curl --fail-with-body -X POST "$API_URL/files/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -F 'file=@problems.json'

# 用上传返回的 data.file.id 提交异步导入。
curl --fail-with-body -X POST "$API_URL/problems/import" \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  --data '{"file_id":"REPLACE_WITH_FILE_ID","mode":"append"}'
curl --fail-with-body "$API_URL/imports/REPLACE_WITH_JOB_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 或直接上传并同步导入；validate 必须为 true/1。
curl --fail-with-body -X POST "$API_URL/problems/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'file=@problems.json' -F 'mode=append' -F 'validate=true'

curl --fail-with-body -X POST "$API_URL/configs/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'file=@config.yaml' -F 'config_type=harness'
curl --fail-with-body "$API_URL/configs/templates/vanilla" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
curl --fail-with-body "$API_URL/problems/export?format=json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" --output problems-export.json
```

`mode=overwrite` 会替换自己的题库。配置模板名称从 `/configs/templates` 获取，响应的 `data.config`
为配置对象。上传配置会移除凭证，返回 `credentials_removed`。

题库导出支持 `json/csv`；运行结果 `/results/{run_id}/download` 与 `/export` 是同一处理器的别名，
支持 `json/csv/md/markdown/html/png/zip`。仅已发布的运行附件可被这些文件导出接口读取；
它们与 `/reports/*` 从业务结果库生成报告的接口使用不同的数据来源。

原始文件下载按后缀返回 JSON、YAML、CSV、PNG、ZIP 或二进制媒体类型。
报告接口分别返回 `text/markdown`、`text/html`、`text/csv`；日志下载返回包含 JSONL 的 `text/plain`。
检查 `Content-Disposition` 获取文件名；日志下载还通过 `X-Retained-Log-Count`、
`X-Exported-Log-Count`、`X-Log-Export-Truncated` 说明保留量、导出量和截断情况。

## 响应和错误码

JSON 成功响应为 `{ "success": true, "data": ..., "message": "..." }`。
列表常使用 `data.items/total/limit/offset/has_more`；具体 data 结构见每个操作的成功示例。
`204` 没有响应体（例如删除评估、退出登录），不要调用 JSON 解析。
下载响应是附件，下载失败仍返回以下标准 JSON 错误。

```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Request validation failed",
    "details": {"problem_ids": "List should have at least 1 item after validation, not 0"},
    "request_id": "req_example"
  },
  "message": "Request validation failed",
  "detail": "Request validation failed",
  "details": {"problem_ids": "List should have at least 1 item after validation, not 0"}
}
```

`error.code` 用于程序判断，`message` 用于展示，`details` 包含结构化或字段级详情。
顶层 `message/detail/details` 是兼容字段。`error.request_id` 与响应头 `X-Request-ID` 相同，
可用于日志关联；请求 ID 由服务器生成。内部错误不暴露原始异常或凭证。

普通 HTTP 错误的默认映射如下，OpenAPI 也包含各状态的错误模型与示例：

- 400 `INVALID_PARAMETER`：请求校验或业务参数/状态错误。**参数校验不是 FastAPI 默认的 422。**
- 401 `UNAUTHORIZED`：缺少凭证或登录凭证错误；`INVALID_TOKEN` 为显式令牌无效/过期错误。响应包含 `WWW-Authenticate: Bearer`。
- 403 `FORBIDDEN`：例如调用者不是管理员。
- 404 `RESOURCE_NOT_FOUND`：资源不存在或不可访问。
- 405 `METHOD_NOT_ALLOWED`：路径不支持该 HTTP 方法。
- 408 `REQUEST_TIMEOUT`：例如上传超时。
- 409 `DUPLICATE_RESOURCE`：例如用户名/邮箱冲突；普通 HTTPException(409) 也使用此默认码。
- 413 `PAYLOAD_TOO_LARGE`：请求体、上传或导出超限。
- 415 `UNSUPPORTED_MEDIA_TYPE`：例如上传未使用 multipart。
- 429 `RATE_LIMIT_EXCEEDED`：请求频率或传输容量超限，保留 `Retry-After`。
- 500 `INTERNAL_ERROR`：通用内部错误，消息为 `An unexpected error occurred`。
- 503 `SERVICE_UNAVAILABLE`：通用服务不可用，消息为 `Service is unavailable`。
- 未单独映射的 HTTP 4xx 为 `HTTP_ERROR`，未单独映射的 5xx 为 `INTERNAL_ERROR`。

错误枚举还包含显式业务码 `BUDGET_EXCEEDED`、`QUOTA_EXCEEDED`、`TASK_ALREADY_RUNNING`、
`SANDBOX_UNAVAILABLE`、`DATABASE_ERROR`；只有调用点显式抛出对应 `ApiError` 时才使用这些码，
不会根据英文消息或同一状态码推断。它们出现在枚举中不代表每个端点都可能返回。
全局错误模型在每个操作下复用；具体触发条件以操作说明为准。

## WebSocket 实时进度

WebSocket 不属于 OpenAPI 的 HTTP paths。地址为
`ws://localhost:8000/api/v1/ws/progress?token=ACCESS_TOKEN`（TLS 部署使用 `wss://`）。
访问令牌通过查询参数传入，不是刷新令牌或 LLM 提供商 Key。

可使用 curl 诊断 HTTP 升级握手（交互收发帧使用 WebSocket 客户端）：

```bash
curl --http1.1 --no-buffer -i \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  "http://localhost:8000/api/v1/ws/progress?token=$ACCESS_TOKEN"
```

浏览器客户端示例：

```javascript
const socket = new WebSocket(
  `ws://localhost:8000/api/v1/ws/progress?token=${encodeURIComponent(accessToken)}`
);
socket.onopen = () => socket.send(JSON.stringify({action: "subscribe", task_id: evaluationId}));
socket.onmessage = event => console.log(JSON.parse(event.data));
// 心跳：socket.send(JSON.stringify({action: "ping"}));
// 取消订阅：socket.send(JSON.stringify({action: "unsubscribe", task_id: evaluationId}));
```

`task_id` 使用自己评估的 ID。连接后收到 `connected`；订阅后收到 `task.snapshot` 和 `subscribed`，
随后转发 `task.started/task.progress/problem.completed/task.completed` 等工作事件。
取消订阅收到 `unsubscribed`，ping 收到 `pong`。无效令牌关闭码为 `4401`；
任务不存在或不属于自己为 `4403`。WebSocket 不使用 HTTP 错误包装。

## 文档维护和验证

增加或修改路由时同步维护对应描述、参数语义和业务示例；自动模型保留实际校验约束和安全依赖。
文档测试会检查所有当前 HTTP 操作的文档覆盖、JSON 样本、公共元数据字段、错误协议、附件媒体类型和公开入口：

```bash
pytest tests/test_api_documentation.py --no-cov
```

其他专题：[文件服务](docs/api-files.md)、[认证](docs/api-authentication.md)、
[监控与配额](docs/api-monitoring.md)。

## 队列健康与 worker 负载

管理员可设置 `MONITOR_QUEUE_PROBES_ENABLED=true`，启用 `/health/redis`、
`/health/workers` 及 `/system/health`、`/system/status` 中的 Redis/Celery 观测。
升级后重启 worker，加载只返回安全数值的 `monitoring_snapshot` 命令。
探测有超时、缓存和并发限制，未知或部分观测不伪造聚合值。

worker 计数只覆盖截止时间内回复的节点，不能视作完整集群；数据库 `pending` 数量
不是 broker 队列长度。主线已通过 AlgorithmHarness 执行评估，但健康检查不验证
某个提供商、凭据或沙箱的运行就绪。真实 LLM 性能、容器资源及新增配额仍属
#157 后续范围，完整配置和限制见[监控指南](docs/api-monitoring.md)。
