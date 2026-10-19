## Why

Issue #158 第 1、2 节要求完整的 API 文档。现有 FastAPI 已生成 OpenAPI 和交互界面，但多数端点缺少参数语义、业务响应示例、认证/限流及 curl 用法，下载接口的媒体类型也不完整。

## What Changes

- 集中维护现有 HTTP 端点的文档元数据，并通过 FastAPI 自动生成的规范展示。
- 补全请求字段、请求/响应示例、统一错误说明、认证与限流要求、curl 示例。
- 说明下载媒体类型、204 空响应、202 异步受理和 WebSocket 协议。
- 添加文档覆盖与真实协议一致性检查以及使用指南。

## Capabilities

### New Capabilities

无。仅完善现有 API 的文档，不新增业务能力或公共 API。

### Modified Capabilities

无。保留现有行为和规范要求，使用 `skip_specs: true`。

## Impact

涉及 `api/main.py`、集中式文档模块、API 使用指南和文档验证测试。不涉及 issue 的测试基础设施、集成/性能测试或版本策略章节。隔离方式由用户选择为新建分支，实际分支为 `comet/api-documentation`。
