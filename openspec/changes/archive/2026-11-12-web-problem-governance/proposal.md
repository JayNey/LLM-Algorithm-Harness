## Why

[#473](https://github.com/JayNey/LLM-Algorithm-Harness/issues/473) 需要让用户在 Web 题库中审核标签与难度变更，并把审核结果用于后续评估。当前 CLI 已提供标签标准化和难度校准逻辑。

## What Changes

- 对选定个人题目预览标签标准化、建议标签和基于本人历史评估的难度建议。
- 按题审核并保存选中的变更，生成可重新打开的个人题集版本。
- 从版本发起评估时使用该版本的题目内容与元数据，保留题目 ID。

## Capabilities

### New Capabilities

### Modified Capabilities

- `frontend/problems-management`：新增批量治理、版本访问与发起评估的验收场景。

## Impact

个人题库 API、历史结果读取、题库页面和评估创建及执行。已确认在功能分支继续使用 Comet Tweak。
