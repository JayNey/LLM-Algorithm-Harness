## Why

现有健康接口已区分存活、就绪与管理员诊断，但尚未定义哪些依赖阻塞 API 接收流量，也未说明 `not_checked` 的准入含义。需要先形成可审阅的规则，避免将诊断成功或后台执行能力当成 API 就绪证明。

## What Changes

- 在 `docs/api-monitoring.md` 定义基础 API、异步提交、后台执行三种作用范围的依赖规则。
- 明确数据库、Redis broker、worker 和沙箱的故障、未检查与观测范围限制，并给出验收示例。
- 明确这是后续实现的判定规则；现有 `/health/ready` 保持未实现，业务路由、监控开关与返回契约均不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。本次只交付规则文档，不改变运行时行为，使用 `skip_specs: true`。就绪端点及流量准入实现需在后续 change 中按本规则建立对应规格与测试。

## Impact

仅修改健康接口文档及本 change 产物。不新增 public API、数据表、探测器或依赖，不修改部署探针。
