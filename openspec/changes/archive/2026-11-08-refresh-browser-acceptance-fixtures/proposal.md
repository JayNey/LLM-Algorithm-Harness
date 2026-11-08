## Why

[#400](https://github.com/JayNey/LLM-Algorithm-Harness/issues/400) 发现旧浏览器验收脚本与当前页面及通知契约脱节，导致正常请求被记录为未知请求，题库和设置场景因定位超时而中断。

## What Changes

- 补齐浏览器脚本的持久化通知读取 fixture，并对齐当前页面、权限与 API 样本。
- 更新失效选择器及验收运行说明，复跑七个受影响的脚本和前端工程检查。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

无。范围限于前端验收脚本及其运行说明。

## Impact

涉及 `frontend/scripts/` 和 `docs/frontend/QA.md`。
