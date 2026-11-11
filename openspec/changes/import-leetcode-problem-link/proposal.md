## Why

[#467](https://github.com/JayNey/LLM-Algorithm-Harness/issues/467)：将公开 LeetCode 单题加入个人题库目前要先运行 CLI 再上传文件，网页应能直接从链接导入。

## What Changes

- 新增 LeetCode 国际站公开单题链接导入，展示等待、成功、重复和失败状态。
- 复用导入器及个人题库事务；成功后刷新题目与来源计数，在个人题目详情中显示来源和人工补全状态。
- 保留 JSON/CSV 导入和现有列表契约；不支持批量、力扣中国站或其他平台。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/problems-management`：扩充个人题库导入入口及个人 LeetCode 题目的详情展示。

## Impact

涉及 Web 题库面板、会话客户端、登录后的新增 v1 接口与个人题库合并逻辑。用户已确认 API 和前后端变更按单一 Tweak 交付，隔离方式为专用分支。
