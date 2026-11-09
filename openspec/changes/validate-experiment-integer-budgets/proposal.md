## Why

实验创建表单会把小数调用次数或 Token 上限发送给后端，随后被整数约束拒绝。前端需要在提交前指出对应字段错误。 [Issue #428](https://github.com/JayNey/LLM-Algorithm-Harness/issues/428)

## What Changes

- 调用次数和 Token 上限按正整数校验，校验失败时在预算限制值字段提示并拦截创建请求。
- 正整数预算继续以数字提交，保留无预算、预算互斥和时间预算的现有规则。
- 补充前端校验测试和实验创建表单场景。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/experiments-management` 的实验创建要求补充整数预算规则及验收场景。

## Impact

涉及前端实验草稿校验、提示文案和测试。后端继续使用现有 `ProblemBudget` schema。
