## Why

[#394](https://github.com/JayNey/LLM-Algorithm-Harness/issues/394) 中，同一登录会话再次进入创建页时，创建协调器仍保留上一个评估的 ID，页面只显示回执。用户需要从已确认的回执开启新草稿。

## What Changes

- 在已确认且请求已结束的回执中提供开启新草稿的操作。
- 保留创建结果未知时的人工核对流程，并验证启动失败后从原评估详情重试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell` 支持在同一登录会话连续创建评估。

## Impact

涉及前端评估创建页、会话内的创建协调器及浏览器 HTTP fixture。
