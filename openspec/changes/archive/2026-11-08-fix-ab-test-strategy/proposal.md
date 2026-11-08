## Why

Issue #396 中，A/B 创建页默认提交生产注册表未注册的 `direct`。API 接收配置后，实际运行在解析策略时失败，无法生成报告。

## What Changes

- 默认使用 `vanilla`，表单仅接受现有策略目录中的值。
- API 在保存配置和提交执行任务之前检查策略注册状态。
- 将 A/B 验收样例与生产注册表对齐，验证实际 runner 能完成测试并生成报告。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/abtest-management`：创建表单默认值及策略目录校验。
- `api/experiment-management`：A/B 创建和启动的策略校验。

## Impact

涉及 A/B 创建表单、A/B API 服务与现有验收测试。复用评估选项目录和生产策略注册表。
