# API 版本管理

当前 HTTP 契约版本为 **1.1.0**，URL 主版本为 **v1**。业务接口均使用 `/api/v1/...`；公开文档入口仍是 `/docs`、`/redoc` 和 `/openapi.json`。OpenAPI `info.version` 显示契约版本，Swagger UI 和 ReDoc 读取同一份文档。

采用 URL 版本，而非 `API-Version`、`Accept-Version` 或自定义 Accept 媒体类型的 Header 协商：URL 在 curl、代理、日志和客户端中直接可见，不需要版本相关的 `Vary` 缓存规则。Header 不选择版本，例如 `/api/v1/health` 带 `API-Version: 2` 仍请求 v1；未实现的 `/api/v2/health` 返回 404。不要将 v2 静默降级到 v1。

契约版本使用 `MAJOR.MINOR.PATCH`：主版本对应 URL 的 `vMAJOR`，兼容扩展增加次版本，仅说明勘误增加修订版本。版本声明位于 `api/documentation.py` 的 `API_CONTRACT_VERSION`；概览及各操作明确标注 API v1。应用发布版本独立维护，目前健康检查 `data.version` 和 Python 包版本为 `0.1.0`，不用于选择 API 版本。

## 兼容变更与破坏性变更

兼容扩展可以添加新端点、可选请求字段或查询参数。新增响应字段要求客户端忽略未知字段，并确认现有客户端可处理；响应枚举增加值也需检查客户端是否穷举处理。默认值、排序、分页、权限、配额、错误码和副作用都属于契约的一部分，需要结合运行时测试审查。

删除或重命名端点/字段、提高必填要求、收紧输入约束、修改类型、移除已承诺状态码或媒体类型，以及改变认证或错误语义，均需要作为破坏性变更处理。不能仅因为 OpenAPI 检查通过就认定业务行为兼容。

未来破坏性变更在新的 `/api/v2` 主版本中提供，保留 v1 供既有调用方迁移；发布前必须列出替代接口、字段映射、认证/错误差异及迁移示例，并明确并行支持窗口、退役日期与通知方式。没有公告和迁移窗口不得删除已支持的主版本；本次不预设退役日期，也不实现 v2。

WebSocket `/api/v1/ws/progress` 沿用 URL 主版本。其消息格式和关闭码同样受兼容策略约束，但不会出现在 HTTP OpenAPI 基线中，需运行 `tests/test_api_ws.py` 回归。

## 自动兼容性检查

运行：

```bash
python3 -m pytest tests/test_api_versioning.py tests/test_api_documentation.py -q --no-cov
```

`tests/fixtures/openapi-v1.json` 冻结本次变更前的全部 126 个 HTTP 操作及组件契约。测试直接调用实际应用的 OpenAPI 生成器，不启动 lifespan，不访问数据库、Redis、Docker 或 LLM。现有 GitHub Actions 测试矩阵执行整个 pytest 套件，自动包含此门禁。

门禁允许新增路径、方法和组件，忽略描述、示例、标题等文档注释；既有操作、请求/响应结构、认证、安全方案、约束和全局协议配置发生变化时失败。字段名恰好为 `description` 或 `example` 时仍受保护。这是保守的契约回归检查，可能拦截兼容的 schema 扩展，也可能因 FastAPI/Pydantic 升级引起结构变化而失败。

失败时先检查 pytest 指出的操作或组件，再确认变更是误改、兼容扩展还是破坏性变更。误改应修复；兼容扩展需在 PR 中解释对现有客户端的影响，审查后才可更新基线；破坏性变更应保留 v1 并另建主版本，不能重录基线来放行。基线不得在测试或 CI 中自动更新；确需更新时，从审查过的 OpenAPI 生成同样去除文档注释的 JSON，并提交可读差异。新增操作允许通过门禁，但发布时应将它们加入基线，作为后续版本的保护对象。

评估创建流程在 `EvaluationResponse` 中新增只读响应字段 `can_start`、`can_cancel` 和 `execution_progress`（含 `completed_units`、`total_units`、`percentage`）。本次基线仅同步这些新增字段及 `ExecutionProgress` 组件；原有字段、必填项和请求契约保持不变。现有客户端需忽略未知响应字段，新评估客户端已读取并校验这三个字段。新建评估可以启动、尚不可取消；入队后可能仍为 `pending`，应以操作能力字段判断是否可启动或取消。兼容性门禁继续严格比较既有结构，不自动重录基线。

OpenAPI 门禁覆盖结构契约，不能验证业务语义、动态字典中的未声明字段、WebSocket 帧或外部依赖行为，需与已有 API 单元测试和集成测试一起运行。

模型目录整合在 1.1.0 中扩展既有 `GET /api/v1/config/providers`：省略 `api_key_id` 仍返回静态示例，传入本人密钥时返回动态列表。静态 `source=static_examples`，动态 `source=provider_api`；评测模型响应增加 `source/scope`。已审查现有前端只读取 `provider/models/complete`、忽略未知字段，属于兼容扩展。本次仅定向更新该操作的可选查询参数和 `ModelOptions` 新属性，保持既有必填字段、鉴权、错误语义和兼容门禁不变。
