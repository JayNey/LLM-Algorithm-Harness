## Why

现有测试覆盖必需数据库故障导致未就绪，但 HTTP 层缺少同一实例从故障恢复的完整回归证据。需要保证依赖异常不影响存活检查，且失败缓存不会阻止恢复就绪。

## What Changes

- 补充同一 API 实例正常、依赖异常、依赖恢复的 HTTP 回归测试。
- 覆盖认证、文件、业务数据库与迁移故障，以及探测抛异常和缓存过期恢复。
- 仅补充测试，遵循现有 api/readiness 契约。

## Capabilities

### New Capabilities
无。

### Modified Capabilities
无；现有故障、缓存过期和重新探测契约保持不变，使用 skip_specs。

## Impact

主要涉及 tests/test_api_readiness.py，无新增依赖或运行时 API 变更。
