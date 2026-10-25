## Why

已有数据库探测与就绪规则，但缺少可供流量探针调用的就绪接口。

## What Changes

- 新增公开 GET /api/v1/health/ready，基础数据库就绪为 200，否则 503。
- 复用数据库探测，1 秒响应预算、1 秒进程内缓存、单个在途探测；仅返回 status。
- 更新健康接口文档与行为测试。用户选择继续 tweak、新建分支，既有归档残留保留。

## Capabilities

### New Capabilities
- `api/readiness`: 基础 API 就绪、超时、缓存和最小公开响应。

### Modified Capabilities
无。

## Impact

监控服务、监控路由、新就绪探测包装、测试与监控文档。不新增依赖，不改变部署探针。
