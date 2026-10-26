## Why
issue #157 的旧验收评论及部署指南滞后于监控实现，OpenAPI 的部分指标说明仍描述早期占位能力，容易误判接口语义和部署验证范围。

## What Changes
- 同步 OpenAPI 中缓存、任务、配额及队列说明。
- 更新监控与部署指南，说明健康接口、共享存储要求和检查边界。
- 实际运行相关测试，落盘验收证据并向 issue #157 追加状态说明。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
无；仅同步文档，不改变行为，skip_specs: true。

## Impact
api/documentation.py、docs/api-monitoring.md、docs/deployment/deploy.md、验证报告及 issue #157 评论。不修改冻结契约基线，不新增接口、依赖或部署配置。
