## Why

实验详情在关联任务轮询返回失败时会更新标题，错误提示仍只读取初始实验响应。用户必须刷新页面才能看到失败原因。见 [Issue #415](https://github.com/JayNey/LLM-Algorithm-Harness/issues/415)。

## What Changes

- 详情页在当前关联任务失败时立即显示任务返回的原因，在成功或取消时清除旧错误。
- 观察到任务终态后停止轮询，并有界读取持久化实验详情。
- 沿用实验、关联任务及身份的隔离，避免迟到响应影响当前详情。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/experiments-management` 的异步进度观察要求补充终态错误、对账和隔离的验收场景。

## Impact

涉及实验详情页及现有浏览器回归脚本。复用实验详情与任务查询接口。
