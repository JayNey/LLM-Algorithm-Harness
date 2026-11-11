## Why

[#469](https://github.com/JayNey/LLM-Algorithm-Harness/issues/469) 在个人题库中提供按标签和难度批量导入 LeetCode 公开题的入口，减少逐条提交链接的操作。

## What Changes

- 支持按标签、难度或组合筛选，预览公开题并勾选待导入题目。
- 后台任务逐题追加到当前用户的个人题库，显示进度、成功、跳过重复和失败结果。
- 允许从任务结果中选择可恢复的失败题重试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/problems-management` — 个人题库的 LeetCode 批量筛选、导入和重试。

## Impact

涉及 LeetCode 导入器、个人题库 API 和后台任务，以及现有题目导入面板。已确认继续使用单一 Tweak change，从最新 main 创建独立分支。
