## Context

客户端通过顶层 detail/message/details 解析错误；现有测试也依赖这些字段。自定义异常暂未被生产业务调用。上传边界直接返回 JSON，不能只注册异常处理器。用户已确认此范围继续 tweak。

## Decisions

- 中央 errors 模块提供 ErrorCode、Pydantic 错误模型、统一响应构造器与全局异常处理；ApiError 兼容 HTTPException 的 status_code/detail/headers，允许调用点显式指定业务码。普通 HTTPException 按状态码映射，不通过英文消息匹配业务码。
- 规范 error 对象始终含 code/message/details/request_id；兼容层保留原有 detail 结构和验证 details 字段，error 由旧字符串改为对象。默认 details 为空对象，敏感字段经过现有脱敏工具处理。5xx 只返回通用消息，不回显异常、数据库/SDK 错误或请求输入。
- 请求日志 ASGI 中间件在内层执行前创建 req_<uuid>，忽略外部同名头；同一 scope 复用 ID。响应构造器也设置 X-Request-ID，以覆盖外层 ServerErrorMiddleware 发送的 500。日志记录 ID 与异常类型，不记录原始异常内容。
- 在认证/上传外侧、CORS 内侧设置响应开始前异常边界，发送安全 500 后不重新抛出，防止 Starlette/Uvicorn 二次日志泄漏；已开始的响应仍抛出原异常。CORS 使用上游 preflight_response 决策，仅将拒绝的文本错误转换为规范 JSON，保留所有策略响应头，不放宽策略。错误响应默认 no-store。
- 缺少凭证/登录失败使用 UNAUTHORIZED；无效或过期 token 使用 INVALID_TOKEN，保留 WWW-Authenticate。中间件提前拒绝统一调用构造器，保留 Retry-After、Cache-Control、CORS 和流式上传清理行为。
- 应用注册公共错误模型；以 4XX 默认响应避免 FastAPI 自动声明实际未使用的 422 格式，现有参数校验仍返回 400。
- 错误码目录覆盖 issue 的通用、认证、请求、业务和服务类别。业务专用码由显式 ApiError 选择；普通异常不猜测业务含义，不新增未实现的预算/配额能力。

## Risks / Trade-offs

- 旧客户端若读取 error 字符串需要迁移到 error.code；现有前端使用兼容字段，不需 UI 变更。
- 不改变已有路由 HTTP 状态；自定义 ConflictError 使用标准 409。错误消息保留原有语言，可选国际化暂不实现。
- 请求开始前、生命周期或响应已经开始后的流式异常无法改写为 JSON；仅规范尚可发送 HTTP 错误的路径。WebSocket 保持现状。
