## Context

参见 proposal.md。FastAPI 根据路由和 Pydantic 自动生成规范；认证依赖已公开 HTTPBearer。部分返回类型为开放字典，下载路由直接返回 Response，需人工提供准确语义与示例。

## Goals / Non-Goals

补齐 issue #158 第 1、2 节现有端点文档。保持处理函数、校验、响应体、状态码与认证/限流策略不变；不实现 issue 的其他章节。

## Decisions

- 使用 `api/documentation.py` 集中维护端点说明和实际数据示例，在所有路由注册后安装 OpenAPI 生成函数。基底仍为 FastAPI `get_openapi`，保留自动生成的模型、约束与安全依赖。
- 按实际依赖区分公开认证接口、用户接口、管理员接口和公开存活检查；说明默认限制及对应环境变量，不读取或暴露服务器密钥。
- 明确请求字段及路径/查询参数语义，提供可复制 curl；JSON 请求使用显式有效样本，multipart 使用文件表单示例。
- JSON 成功响应使用端点专用业务样本；204 无响应体；下载声明实际媒体类型与 Content-Disposition。WebSocket 在指南和规范总览中说明握手、帧及关闭码。
- 纯文档补全不新增/修改行为规范，跳过 delta spec。文档测试核对每个现有路由、请求模型样本、认证依赖、响应模型与实际代表性响应；新增路由缺文档时明确失败。

## Risks / Trade-offs

- 开放字典的字段不会自动约束：提供来源于实际服务返回值的样本与说明，并检查关键协议契约。
- 示例 ID 是占位符：指南说明先创建资源再替换 ID；所有凭证仅使用虚构占位符。
- Swagger/ReDoc 默认从 CDN 加载界面资源：说明部署时需允许访问相应 CDN。

## Migration Plan

无需迁移或新增依赖；启动现有服务即可访问 `/openapi.json`、`/docs`、`/redoc`。使用指南更新已有 `API.md`，替换其中过期的请求和错误契约说明，README 提供入口。
