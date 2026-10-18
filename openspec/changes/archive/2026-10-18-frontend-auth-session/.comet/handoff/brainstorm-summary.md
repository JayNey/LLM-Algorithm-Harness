# Brainstorm Summary

- Change: frontend-auth-session
- Date: 2026-10-17

## 确认的技术方案

已确认采用纯模块加 Zustand 和 axios。

- `returnPath`、`tokenStore`、`refreshCoordinator` 不依赖页面和 Vite，供 Node 测试直接调用。
- `http` 是唯一 axios 实例，负责认证头、过期前刷新和 401 单次重试。
- Zustand `auth` store 保存 token、过期时间和用户名。
- `/login` 与 `/register` 使用公开布局；六个既有页面留在带会话守卫的 `AppLayout` 中。
- 登录成功后请求 `/users/me`。登出无论撤销请求是否成功都清除本地会话。

## 关键取舍与风险

- 登录时只保留一种浏览器存储，避免记住我和未记住我互相覆盖后无法判断该恢复哪一份。
- refresh token 只能使用一次，所以并发 401 共用一个刷新 Promise。
- 登录 401 只显示「登录失败」，不区分用户名和密码。
- `/users/me` 的非 401 失败保留 token，导航显示「已登录」。
- 不引入组件测试库。页面靠类型检查和生产构建。

## 测试策略

Node 自带测试运行器覆盖回跳路径、存储选择、单次刷新，以及 HTTP 客户端的 Bearer、登录不刷新和并发 401。页面用 `tsc -b` 和 `vite build`。

## Spec Patch

无。

## 工作区归属

已确认：`openspec/changes/frontend-account-settings/` 保留不处理，不并入本 change，也不删除。
