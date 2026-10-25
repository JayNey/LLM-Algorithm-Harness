## Why
#157 分多轮交付，最新main0e795e4已包含监控、日志、性能、配额及#269统一脱敏配置。原指南仍将已实现能力列为待做，健康响应硬编码pending_issues=[157]，阻碍准确验收。

## What Changes
- 逐项核对原issue44个复选条目，给出源码、定向测试、真实依赖证据与运行边界。
- 清除已完成能力的旧pending标记，保留partial/degraded/not_checked及既有字段/权限，不把部署状态误报为缺代码。
- 更新监控指南/API概览，实跑当前监控/配额/日志/兼容性回归和隔离Docker/Redis/Celery观测。
- 独立Bugbot审查并提交base=main的验收收尾PR，人工决定合并/关闭issue。

## Capabilities
### New Capabilities
- `api/monitoring-status`: 监控能力交付状态与部署观测状态分离。
### Modified Capabilities
无。既有配置、LLM采集和查询统计协议保持，仅更新已实现能力的状态元数据。

## Impact
MonitorService健康元数据、其OpenAPI例子及回归测试；API和监控文档、新验收清单与脱敏证据。无新后端端点、schema、依赖或提供商调用。真实依赖只使用本轮隔离服务及自建容器，不以模拟成功替代外部依赖验证。
