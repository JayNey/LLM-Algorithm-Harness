## Why

Issue #161 要求登录表单在客户端校验。登录页现在接受空的用户名或邮箱、空密码，并直接发送登录请求。注册页已经在校验失败时停在页面上。

## What Changes

- 登录页在发送请求前检查用户名或邮箱、密码是否为空，以及是否超过接口允许的长度
- 未通过时指出对应字段，且不发送登录请求
- 不改登录接口、记住我、错误密码提示和登录成功后的跳转

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `frontend/auth-session`: 登录提交前完成客户端校验，未通过时不发请求

## Impact

- `frontend/src/pages/Auth/LoginPage.tsx`
- 登录校验函数及其测试
- 不改后端认证接口
