## Why

登录会话建立后，用户仍然不能查看或修改自己的资料，也不能管理评估要使用的 LLM API 密钥。这些后端接口已经可用，Issue #161 的后半部分需要把它们接到设置页。

## What Changes

- 设置页改为个人资料和 API 密钥的入口，页面本身不请求业务数据
- 新增个人资料页：展示用户名、邮箱和注册时间，并允许修改用户名和邮箱
- 新增 API 密钥页：按 `openai`、`anthropic`、`siliconflow` 分组，支持添加、修改名称、确认后删除和验证，并展示使用次数与最后使用时间
- 界面不接收、不展示密钥明文、掩码或后四位；后端响应里也没有这些值
- 未登录用户不能打开资料页和密钥页
- 不修改后端接口，也不重做登录、刷新和路由守卫

## Capabilities

### New Capabilities

- `frontend/user-profile`: 查看和修改当前用户的用户名、邮箱，并展示注册时间
- `frontend/api-keys`: 管理当前用户的 LLM API 密钥元数据和验证状态

### Modified Capabilities

无。六个既有页面的行为不变；资料和密钥是设置页下的新路由。

## Impact

- `frontend/src` 的设置入口、资料页、密钥页，以及对应的请求封装
- 依赖 `frontend-auth-session` 已提供的登录会话、认证请求客户端和路由守卫
- 调用 `GET /api/v1/users/me`、`PATCH /api/v1/users/me`、`GET /api/v1/api-keys`、`POST /api/v1/api-keys`、`PATCH /api/v1/api-keys/{id}`、`DELETE /api/v1/api-keys/{id}` 和 `POST /api/v1/api-keys/{id}/verify`
