## Why

Issue #158 第 8 节要求统一错误格式和错误码。目前自定义异常、HTTPException 和中间件提前拒绝使用多种格式，客户端无法稳定分类和关联诊断。

## What Changes

- **BREAKING**：旧字符串 error 改为对象，所有 HTTP 错误使用 error.code/message/details/request_id；保留 success=false 和兼容的顶层 message/detail/details，现有前端无需改动。
- 定义稳定大写错误码、HTTP 默认映射及显式业务异常入口；请求 ID 由服务端生成并返回 X-Request-ID。
- 覆盖认证、上传边界、参数校验、框架 404/405 和未处理异常；保留认证与限流响应头，内部异常不泄漏实现信息。
- 注册 OpenAPI 错误模型，文档说明兼容字段、错误码和可选国际化的范围。

## Capabilities

### New Capabilities

- `api/error-handling`: 统一 HTTP 错误契约、码体系、关联标识和兼容语义。

### Modified Capabilities

无。成功响应、WebSocket 帧与关闭码、任务结果中的业务失败记录保持原协议。

## Impact

错误处理、请求日志、认证与上传中间件、应用文档注册、认证服务，以及契约测试和 README；不修改数据库与前端 UI。用户已选择 2A：从最新 main 建独立分支，确认涉及公开契约/多个错误出口时继续单一 tweak；兼容字段避免前端同步迁移。可选国际化不在本次范围。
