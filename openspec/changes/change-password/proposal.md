## Why

Issue #161 要求已登录用户能在个人资料里修改密码。资料页目前只能改用户名和邮箱，后端也没有校验当前密码并更换口令的接口。

## What Changes

- 新增已登录用户修改密码的接口：校验当前密码，按注册规则保存新密码
- 个人资料页增加修改密码表单，包含当前密码、新密码、确认密码和客户端校验
- 不改登录、刷新、登出和资料中的用户名、邮箱行为
- 不新增角色、头像或忘记密码

## Capabilities

### New Capabilities

- `api/password-change`: 已登录用户提交当前密码和新密码后，校验通过才更新口令

### Modified Capabilities

- `frontend/user-profile`: 资料页增加修改密码，校验失败不发请求，成功后给出明确结果

## Impact

- `api/auth` 的请求模型、存储更新和路由
- `frontend/src/pages/Settings/ProfilePage.tsx` 与资料校验
- 现有认证测试和前端资料测试
