# Comet Design Handoff

- Change: frontend-auth-session
- Phase: design
- Mode: compact
- Context hash: 4bbbb83a63d03e252023db5edf0f32638070a15dbb52772c0fe7aff9d88bf76c

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/frontend-auth-session/proposal.md

- Source: openspec/changes/frontend-auth-session/proposal.md
- Lines: 1-28
- SHA256: cbc66b836bcec037f81cc0f08c472d269535b032f08abe0e353bf98f76d18bc7

```md
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

```

## openspec/changes/frontend-auth-session/design.md

- Source: openspec/changes/frontend-auth-session/design.md
- Lines: 1-63
- SHA256: 84190109eebd82fde1119c306d6cee9b4f962883059f1828cec99271ebb8359b

```md
## Context

前端是 Vite + React + React Router + Ant Design + Zustand。`AppLayout` 包住六个占位页，未知路径回到仪表盘。API 基址来自 `VITE_API_BASE_URL`，开发服务器把 `/api` 代理到本机后端。认证接口已经返回 `success/data/message`；登录和刷新的 `data` 含 `access_token`、`refresh_token`、`token_type` 和 `expires_in`。登出返回 204。注册只返回公开资料，不返回 token。当前用户是 `GET /api/v1/users/me`。刷新 token 只能使用一次。

## Goals / Non-Goals

**Goals:**

- 用一个 HTTP 客户端完成认证头注入和单次刷新
- 记住我决定会话能否在浏览器重新打开后保留
- 登录页和注册页与六个业务页分开，避免未登录时闪出业务内容

**Non-Goals:**

- 不解析 JWT 来得到用户名；身份只来自 `/users/me`
- 不在本 change 接入 WebSocket 认证
- 不新增后端，也不把 token 放到 cookie 或 URL

## Decisions

### 1. 记住我用两种浏览器存储

选择记住我时，access token、refresh token、过期时间和用户资料写入 `localStorage`。未选择时写入 `sessionStorage`。应用启动时只从一个存储恢复会话。

备选是一律写入 `localStorage`，无法表达“不记住我”。另一备选是只放内存，刷新页面就会掉线。`sessionStorage` 不能跨标签页，这是不记住我的可接受代价。

### 2. 单一 axios 实例，刷新合并为一次

HTTP 客户端使用 `readViteEnv().apiBaseUrl`。请求拦截器在 access token 距过期不足 30 秒时先刷新，否则附上当前 Bearer。响应遇到 401 时，注册、登录、刷新和登出请求直接失败；其他请求共用同一个进行中的刷新 Promise，成功后重试一次。刷新请求在 body 中提交 `refresh_token`，不附带旧的 access token。

备选是每个 401 各自刷新。后端使旧 refresh token 失效，并发刷新会让后续请求失败。

### 3. 公开路由和受保护路由分开

`/login` 和 `/register` 使用只含应用名、配色切换和登录/注册入口的布局。六个既有页面留在 `AppLayout` 内，并由路由守卫检查会话。守卫把原路径存为以单个 `/` 开头、且不以 `//` 开头的站内路径；不符合的值回到 `/`。已登录用户打开登录或注册页时进入仪表盘。

备选是所有页面继续共用现在的导航，未登录时用条件隐藏六个链接。那样业务页仍会先挂载，和“不展示题目内容”冲突。

### 4. 登录后再读取当前用户

登录成功只保存 token，然后请求 `/users/me`。导航显示 `username`。注册成功只跳到登录页并提示可以登录，不建立会话。登出先尽力调用 `POST /api/v1/auth/logout`，无论结果如何都清除本地会话并进入登录页。

表单使用已有的 react-hook-form。密码框不明文显示。注册页用长度分档提示密码是否达到 12 字符、以及是否达到 16 字符，不把密码发到额外接口。

备选是登录响应里直接带用户资料。当前登录响应没有这份资料。

### 5. 纯逻辑用现有 Node 测试运行

回跳路径判断、存储选择和刷新合并不依赖新测试框架，用 Node 自带测试运行器覆盖。页面行为沿用现有的类型检查和生产构建。

备选是引入 Vitest 和 Testing Library。那会新增依赖，而本 change 的高风险点是 token 流程，不是组件渲染。

## Risks / Trade-offs

- [refresh token 只能使用一次] → 所有并发 401 等待同一次刷新；刷新请求本身不再进入 401 重试
- [localStorage 可被同源脚本读取] → 只保存会话 token 和公开资料，不保存 API 密钥；后端当前不签发 cookie
- [登录失败也是 401] → 登录、注册、刷新、登出不进入自动刷新
- [sessionStorage 不跨标签页] → 仅用于未勾选记住我的会话
- [六个页面变为必须登录] → 这是提案中的行为变化；回滚时恢复前端构建即可，没有数据迁移

## Migration Plan

先部署已包含这些路由的前端静态资源。后端接口保持不变。回滚时发布上一版前端；已写入浏览器存储的 token 会在旧前端被忽略，用户重新打开即可。

```

## openspec/changes/frontend-auth-session/tasks.md

- Source: openspec/changes/frontend-auth-session/tasks.md
- Lines: 1-24
- SHA256: 9386c59a8b924b0ee9b73ff5dd271aa342c82f58e661db4d125db90e7cdb82d8

```md
## 1. 会话基础

- [ ] 1.1 实现站内回跳路径判断：只接受以单个 `/` 开头且不以 `//` 开头的路径，其余回到 `/`。用 Node 测试验证外部网址、协议相对地址和题目路径
- [ ] 1.2 实现记住我的存储选择：勾选时使用 `localStorage`，未勾选时使用 `sessionStorage`，并只从一个存储恢复会话。用 Node 测试验证两种选择和恢复结果

## 2. HTTP 与认证状态

- [ ] 2.1 增加使用 `VITE_API_BASE_URL` 的 axios 客户端，解包 `success/data/message`，并在 access token 距过期不足 30 秒时先刷新。用 Node 测试验证受保护请求带 Bearer，登录、注册、刷新和登出不进入自动刷新
- [ ] 2.2 实现单次刷新：并发 401 共用一个刷新 Promise，成功后原请求重试一次，失败则清除本地会话。用 Node 测试验证只发出一次刷新请求
- [ ] 2.3 增加认证 store：保存 token、过期时间、当前用户名，并提供登录、恢复和清除。登录成功后请求 `GET /api/v1/users/me`。用 Node 测试或 store 级测试验证清除后不再恢复会话

## 3. 页面与路由

- [ ] 3.1 增加注册页：校验用户名、邮箱、12–1024 位密码和确认密码，密码不明文显示，并给出长度分档提示。校验失败不发请求；成功后进入登录页并提示可以登录。用类型检查确认表单组件通过编译
- [ ] 3.2 增加登录页：接受用户名或邮箱、密码和记住我，错误时留在登录页，成功后回到站内原地址或仪表盘。进行中的提交显示加载状态，回车可提交。用类型检查确认页面通过编译
- [ ] 3.3 把 `/login` 和 `/register` 放到公开布局，六个既有页面放到会话守卫之后。未登录打开这些页面或未知路径时进入登录页；已登录打开登录或注册页时进入仪表盘。用生产构建确认新增路由被分割加载

## 4. 导航与登出

- [ ] 4.1 已登录导航显示用户名和登出，未登录导航显示登录与注册，窄屏下这些入口仍可达，配色切换保持可用。登出调用 `POST /api/v1/auth/logout`，失败也清除本地会话并进入登录页。用类型检查和生产构建确认布局通过

## 5. 整体验证

- [ ] 5.1 运行前端类型检查、代码检查和生产构建，三者都成功退出。Node 会话测试覆盖回跳、存储选择和单次刷新

```
