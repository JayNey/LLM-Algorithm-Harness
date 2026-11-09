## Why

题库评估历史抽屉在切换题目时沿用上一题的页码，可能把有记录的题目显示为空。[Issue #427](https://github.com/JayNey/LLM-Algorithm-Harness/issues/427) 要求切换时从首页加载，并隔离上一题的迟到响应。

## What Changes

- 按题目隔离评估历史抽屉的分页和请求状态。
- 通过浏览器 fixture 验证切题、迟到响应、同题翻页和真实空历史。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/problems-management` 明确评估历史的切题与分页行为。

## Impact

涉及题库页面的评估历史抽屉、浏览器验收脚本与题库管理规格。沿用现有评估历史接口。
