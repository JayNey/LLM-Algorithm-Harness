---
comet_change: frontend-auth-session
role: technical-design
canonical_spec: openspec
archived-with: 2026-10-18-frontend-auth-session
status: final
---

# 前端登录会话 — 技术设计（Design Doc）

> 本文深化 open 阶段 `openspec/changes/frontend-auth-session/design.md`。canonical 需求以 OpenSpec delta spec 为准：`openspec/changes/frontend-auth-session/specs/frontend/auth-session/spec.md` 和 `openspec/changes/frontend-auth-session/specs/frontend/app-shell/spec.md`。

## 1. 意图

六个占位页需要先有登录会话，后续资料和密钥页面才能复用同一套认证请求。后端已经提供注册、登录、刷新、登出和当前用户查询。本设计只规定前端会话如何存储、刷新和守卫路由。

## 2. 目标 / 非目标

**目标**

- 回跳、存储和刷新协调是不依赖 Vite 的纯模块。
- 全应用只有一个 axios 实例负责 Bearer 和单次刷新。
- 公开页面和六个业务页面分开渲染。

**非目标**

- 不实现资料编辑、API 密钥、改密码、头像和角色权限。
- 不解析 JWT，不把 token 放到 cookie 或 URL。
- 不接入 WebSocket 认证，不新增测试框架。

## 3. 模块

| 模块 | 职责 | 依赖 |
| --- | --- | --- |
| `frontend/src/auth/returnPath.ts` | 把回跳地址收成站内路径 | 无 |
| `frontend/src/auth/tokenStore.ts` | 读写并清空浏览器存储 | 注入的 `Storage` |
| `frontend/src/auth/refreshCoordinator.ts` | 把并发刷新收成一个 Promise | 注入的刷新函数 |
| `frontend/src/auth/http.ts` | axios、认证头、解包和错误 | 以上三个模块、`readViteEnv` |
| `frontend/src/store/auth.ts` | 会话状态、登录、恢复、登出 | `http`、`tokenStore` |
| `frontend/src/layouts/AuthLayout.tsx` | 应用名、配色、登录/注册入口 | 现有配色 store |
| `frontend/src/components/Auth/RequireSession.tsx` | 未登录时替换业务页 | `auth` store、`returnPath` |
| `frontend/src/pages/Auth/LoginPage.tsx` | 登录表单 | `auth` store、react-hook-form |
| `frontend/src/pages/Auth/RegisterPage.tsx` | 注册表单和长度提示 | `http`、react-hook-form |

`App.tsx` 把 `/login`、`/register` 放在 `AuthLayout` 下，六个既有页面放在 `RequireSession` 和 `AppLayout` 下。已登录用户访问登录或注册页时进入 `/`。

## 4. 纯模块契约

`sanitizeReturnPath` 只接受以单个 `/` 开头且不以 `//` 开头的字符串。空值、外站地址和协议相对地址都返回 `/`。

`StoredSession` 包含 `accessToken`、`refreshToken`、`expiresAt`（毫秒）和 `username`。`writeSession(remember, session)` 写入对应存储，并删除另一种存储。`readSession()` 先读 `localStorage`，没有再读 `sessionStorage`。`clearSession()` 删除两边。测试注入内存 `Storage`，生产代码使用浏览器存储。

`createRefreshCoordinator(run)` 返回 `refresh()`。已有进行中的 Promise 时直接返回它；结束后清空，下一次失败可以再试。`run` 在调用时读取当时的 refresh token。

## 5. 数据流

客户端把 `VITE_API_BASE_URL` 用作 axios `baseURL`。开发值是 `http://localhost:8000/api/v1`，生产值是 `/api/v1`。请求路径相对于这个根，不再重复 `/api/v1`。拼好后的地址仍是 `/api/v1/auth/login`、`/api/v1/auth/register`、`/api/v1/auth/refresh`、`/api/v1/auth/logout` 和 `/api/v1/users/me`。

登录：表单调用 store。`POST /api/v1/auth/login` 不带 Bearer。成功后用 `expires_in` 计算 `expiresAt`，按记住我写入存储，再 `GET /api/v1/users/me`。资料成功后写入 `username` 并跳到回跳地址。注册成功只跳到 `/login` 并提示可以登录，不写 token。

受保护请求：距过期不足 30 秒时先刷新，再设置 `Authorization: Bearer`。路径以 `/auth/login`、`/auth/register`、`/auth/refresh` 结尾的请求不刷新、不附带 access token。登出请求附带当前 access token。access token 将过期，或登出本身返回 401 时，先走同一次刷新，再用新 access token 重试登出一次，然后停止。刷新请求的 body 是 `{ "refresh_token": "..." }`。其他请求遇到 401 时走同一次刷新并重试一次。刷新失败则 `clearSession` 并进入登录页，回跳地址是当前站内路径。

登出：尽力 `POST /api/v1/auth/logout`，并带上当前 access token。无论状态码如何都清除本地会话并进入登录页。204 没有 JSON，客户端不得把空响应当成解析失败。

## 6. 错误处理

成功响应读取 `data`。认证路由的失败体是 `{ "detail": "..." }`，请求校验失败体是 `{ "message", "details" }`。

- 登录 401：显示「登录失败」。
- 409：显示「用户名或邮箱不可用」，保留用户名和邮箱，清空密码。
- 400 且有 `details`：显示到对应字段。没有字段信息时显示「请求无效」。
- 429：显示「请求过于频繁，请稍后再试」。
- 网络错误和 5xx：显示「服务暂时不可用」。
- `/users/me` 在登录后返回非 401：保留 token，导航显示「已登录」。
- 密码长度提示只分三档：不足 12 位、已达到 12 位、16 位及以上。

## 7. 测试

在 `frontend/package.json` 增加 Node 测试脚本，使用 `node --experimental-strip-types --test`，不新增依赖。

- `returnPath`：站内路径保留，外站地址和 `//` 回到 `/`。
- `tokenStore`：记住我只留 `localStorage`，不记住我只留 `sessionStorage`，恢复时优先本地存储。
- `refreshCoordinator`：并发调用只执行一次，失败后可以再次调用。
- `http`：用 axios 自定义 adapter。受保护请求带 Bearer；登录请求不触发刷新；两个并发 401 只刷新一次。

页面不写组件测试。完成标准是前端类型检查、代码检查和生产构建成功。

## 8. 风险

- 两个浏览器存储同时有旧数据时，启动优先采用 `localStorage`。登录写入会清掉另一种，避免新会话和旧会话并存。
- 刷新函数必须在发起请求时读取 token。提前绑定旧 token 会在轮换后重复使用已失效的 refresh token。
- 登录接口本身返回 401。它必须排除在自动刷新之外，否则错误密码会触发刷新循环。
