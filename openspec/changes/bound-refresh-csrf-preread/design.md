## 实现

在 explicit_refresh_token 中按块累计字节，超过 16384 时在追加和拼接前抛出统一边界错误。以事件循环单调时钟计算整次读取的 10 秒截止时间，每次 receive 用剩余时间执行 asyncio.wait_for；总时限覆盖持续滴流和空分块。超时抛出 408 边界错误，断连使用 ClientDisconnect 直接结束，不进入下游。

CsrfMiddleware 仅在预读调用处处理边界错误和断连，复用 error_response 保留统一错误码、请求 ID、no-store 和外层 CORS。完整且合规 body 沿用单次回放及 JSON token 优先规则，不改变中间件顺序。

## 验证

真实 create_app ASGI 调用覆盖有/无 CSRF 头、单大块/累计超限、精确上限、慢读取/持续分块总超时、断连和 token 优先。现有 HTTP SQLite 测试覆盖合法 cookie 刷新及 403。
