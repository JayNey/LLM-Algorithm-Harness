## Why
现有镜像存活检查不能代表数据库可用，生产 nginx 尚未按已实现的就绪接口准入，部署文档仍宣称接口未实现。

## What Changes
- 镜像存活探针继续使用 `/api/v1/health`。
- nginx 在业务请求（含认证与 WebSocket 握手）前查询就绪接口，失败关闭准入并返回 503；健康检查和管理员诊断可独立访问。
- 更新部署说明及外部 HTTP 监控告警配置示例，业务可用性只认就绪 HTTP 200。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `deployment`: 细化反向代理就绪准入与探针、告警职责。

## Impact
仅调整 nginx 部署配置、部署文档、监控说明及部署回归测试；不改应用路由或数据库，不引入监控服务。
