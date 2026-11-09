## Why

[#433](https://github.com/JayNey/LLM-Algorithm-Harness/issues/433) 的表单和 API 拒绝零价，现有 OpenSpec 已规定价格非负，并把零价视为已知定价。产品决定是继续支持零价，允许输入和输出分别免费。

## What Changes

- 表单、API 和前端响应解析统一接受有限非负单价，表单提示说明 `0` 表示免费。
- 验证零价覆盖可保存、回读并保留历史，费用统计将已知零成本和缺失价格分别处理。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/pricing-management` 说明零价语义及表单与回读契约。
- `api/cost-management` 明确覆盖定价 API 的非负边界及版本回读。

## Impact

涉及定价页面、定价客户端、定价覆盖请求 schema 和兼容性基线。复用现有定价版本持久化及费用统计。
