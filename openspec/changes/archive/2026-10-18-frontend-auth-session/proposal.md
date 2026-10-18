## Why

前端外壳已有六个页面，但用户无法建立会话。后端已经提供注册、登录、刷新、登出和当前用户查询。Issue #161 需要先把这层会话接上，个人资料和 API 密钥页面才能在已登录状态下工作。

## What Changes

- 新增登录页和注册页，包含客户端校验、错误提示、加载状态和记住我
- 新增 access token 与 refresh token 的存储、过期刷新，以及给受保护请求自动附加 `Authorization: Bearer`
- 新增导航栏中的当前用户身份和登出
- **BREAKING**：未登录时，仪表盘、题目、评估、结果、实验和设置不再直接展示，而是进入登录页；登录成功后回到原地址
- 不修改后端认证接口，也不在本 change 中实现资料编辑或 API 密钥管理

## Capabilities

### New Capabilities

- `frontend/auth-session`: 注册、登录、记住我、token 刷新、请求认证头、路由守卫和登出

### Modified Capabilities

- `frontend/app-shell`: 六个既有页面在没有会话时进入登录页。已有会话时，即使后端不可用，这些页面仍可打开且不请求业务数据。未登记路径在已登录时仍显示仪表盘。

## Impact

- `frontend/src` 的路由、应用布局、登录/注册页面、认证状态、token 管理和 HTTP 客户端
- 使用现有的 axios、Ant Design、react-hook-form、Zustand 和 React Router，不新增后端依赖
- 调用 `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`POST /api/v1/auth/logout` 和 `GET /api/v1/users/me`
- 个人资料编辑与 API 密钥管理由后续 change `frontend-account-settings` 承担
