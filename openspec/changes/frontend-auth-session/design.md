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

HTTP 客户端使用 `readViteEnv().apiBaseUrl`。登录、登出和注册共用这一个实例。请求拦截器在 access token 距过期不足 30 秒时先刷新，否则附上当前 Bearer。响应遇到 401 时，注册、登录和刷新请求直接失败。登出请求带上当前 access token；它即将过期或返回 401 时，先走同一次刷新再重试登出一次。其他请求也共用同一个进行中的刷新 Promise，成功后重试一次。刷新请求在 body 中提交 `refresh_token`，不附带旧的 access token。状态码大于等于 500 时，客户端错误消息是「服务暂时不可用」。

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
- [登录失败也是 401] → 登录、注册和刷新不进入自动刷新。登出返回 401 时刷新一次并重试登出一次
- [sessionStorage 不跨标签页] → 仅用于未勾选记住我的会话
- [六个页面变为必须登录] → 这是提案中的行为变化；回滚时恢复前端构建即可，没有数据迁移

## Migration Plan

先部署已包含这些路由的前端静态资源。后端接口保持不变。回滚时发布上一版前端；已写入浏览器存储的 token 会在旧前端被忽略，用户重新打开即可。
