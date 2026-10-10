## Purpose

REST API 核心框架定义通用的 HTTP 端点、中间件、请求验证、错误处理和文档生成能力，为所有后续 API 端点提供基础支撑。

## ADDED Requirements

### Requirement: API 服务启动和基本路由

系统 SHALL 启动 FastAPI Web 服务，监听配置的主机和端口（默认 `localhost:8000`），并提供以下基础路由：
- `/docs` - Swagger UI 文档界面
- `/openapi.json` - OpenAPI schema JSON
- `/api/v1/health` - 健康检查端点

#### Scenario: 服务启动并响应健康检查
- **WHEN** API 服务成功启动
- **THEN** `/api/v1/health` 端点返回 HTTP 200，包含系统健康状态和版本信息

#### Scenario: OpenAPI 文档自动生成
- **WHEN** 服务启动后
- **THEN** `/docs` 和 `/openapi.json` 返回有效的 Swagger UI 和 OpenAPI schema

### Requirement: CORS 跨域支持

系统 SHALL 配置 CORS 中间件，允许来自不同域名的浏览器请求访问 API。

#### Scenario: 跨域请求被正确处理
- **WHEN** 浏览器发起 preflight OPTIONS 请求
- **THEN** 系统返回 HTTP 200 和必要的 CORS 响应头 (Access-Control-Allow-*)

### Requirement: 统一响应格式

所有成功的 API 端点 SHALL 返回统一的 JSON 响应结构：
```json
{
  "success": true,
  "data": { /* 端点特定数据 */ },
  "message": "Operation successful"
}
```
失败响应 SHALL 使用：
```json
{
  "success": false,
  "error": "error-code",
  "message": "Human-readable error message",
  "details": { /* 可选的详细错误信息 */ }
}
```

#### Scenario: 成功的端点调用返回统一格式
- **WHEN** 客户端调用任何成功的端点
- **THEN** 响应包含 `success: true` 和相应的 `data` 字段

#### Scenario: 错误响应遵循统一格式
- **WHEN** 端点遇到错误（如参数验证失败、资源不存在）
- **THEN** 响应包含 `success: false`、错误代码和人类可读的消息

### Requirement: 请求参数验证

系统 SHALL 使用 Pydantic 对所有 API 请求进行自动验证，包括：
- 查询参数（query parameters）的类型和范围验证
- 请求体（JSON payload）的结构和字段验证
- 必填字段检查

#### Scenario: 无效参数被拒绝
- **WHEN** 客户端发送包含无效类型或缺少必填字段的请求
- **THEN** 系统返回 HTTP 400 与详细的验证错误信息

#### Scenario: 有效参数被接受
- **WHEN** 客户端发送格式正确的请求
- **THEN** 请求被处理，不返回验证错误

### Requirement: 错误处理中间件

系统 SHALL 提供全局错误处理机制，捕获所有未处理异常并返回一致的错误响应。

#### Scenario: 服务器错误返回 HTTP 500
- **WHEN** API 处理过程中发生未捕获的异常
- **THEN** 系统返回 HTTP 500 和统一的错误响应格式

### Requirement: 日志记录

系统 SHALL 记录所有 API 请求和响应，包括：
- 请求方法、路径、查询参数
- 响应状态码和处理时间
- 错误信息和堆栈跟踪（仅内部日志）

#### Scenario: 请求被记录
- **WHEN** 任何端点被调用
- **THEN** 系统日志包含请求和响应的详细记录
