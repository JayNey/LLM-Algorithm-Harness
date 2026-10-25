## Why

健康接口的存活、就绪和管理员诊断职责需要统一说明，避免将 API 存活误解为依赖可用或可接收业务流量。

## What Changes

- 明确 `/api/v1/health` 用于存活检查，`/api/v1/health/ready` 用于就绪检查，`/api/v1/system/health` 用于管理员诊断。
- 明确就绪接口当前尚未实现，不能直接配置为部署探针。
- 修正部署文档将存活检查等同迁移完成的表述；同步 OpenAPI 说明。

## Capabilities

### New Capabilities

无。本次仅澄清文档，不新增接口。

### Modified Capabilities

无。不改变现有接口行为、响应及鉴权；使用 `skip_specs: true`。

## Impact

影响监控文档、部署文档和 `api/documentation.py` 中的接口用途说明。无运行时行为、依赖或 schema 变化。
