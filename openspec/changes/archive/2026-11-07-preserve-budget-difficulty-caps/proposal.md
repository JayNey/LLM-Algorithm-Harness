## Why

预算配置尚未加载时，表单可能将未知的难度上限作为空对象保存，覆盖已有配置并影响 worker 执行。[议题 #391](https://github.com/JayNey/LLM-Algorithm-Harness/issues/391)

## What Changes

- 预算读取失败可重试，成功读取后才开放编辑。
- 仅提交变更的预算字段，成功后按服务端响应回填。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/budget-alerts`：补充预算读取、部分更新与回填约定。

## Impact

涉及预算设置表单和回归验证。沿用现有预算 API 的部分更新协议。
