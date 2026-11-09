## Why

[#430](https://github.com/JayNey/LLM-Algorithm-Harness/issues/430) 中，预算和定价页的宽表会撑宽整页，窄屏用户需要横向移动整个页面才能操作表格末列。

## What Changes

- 让预算用量、预警规则与投递历史、费用表、定价目录与历史各自在具名的可聚焦区域内滚动。
- 用含数据的浏览器 fixture 验证两个页面的五档宽度，以及滚动区和末列操作的键盘可达性。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell` 的共享表格行为增加设置页及定价历史抽屉的验收场景。

## Impact

涉及预算页、定价页与现有设置页浏览器 fixture。沿用共享工作流表格样式和现有 API。
