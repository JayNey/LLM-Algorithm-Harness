# frontend-auth-session 验证报告

结论：PASS

## 范围

- change：`frontend-auth-session`
- 分支：`comet/frontend-auth-session`
- 工作流：full。验证模式：full。`comet state scale` 统计任务 12、变更文件 30，结果为 full。
- 基线：计划 `base-ref` `c4a019c0843a2e96c32c09eb67bc363c4a2012ee`。验证时 HEAD 为 `731a33b8b981aac927330b2d10828bdccf657db4`。
- 产物语言：zh-CN。
- 未提交且不属于本 change 的 `openspec/changes/frontend-account-settings/` 保持不处理，不纳入本次验证。

## 集成审查

`review_mode` 为 thorough。

| 审查 | 范围 | 结论 |
| --- | --- | --- |
| 第一次整段审查 | `c4a019c..b915d43` | 不通过。登出去掉了 `Authorization`，服务端会话不会被撤销。已退回实现并修复。 |
| 第二次整段审查 | `c4a019c..ca88ab3` | 不通过。`VITE_API_BASE_URL` 已含 `/api/v1`，请求再传 `/api/v1/...`，实际地址变成 `/api/v1/api/v1/...`。已退回实现并修复。 |
| 本次增量审查 | `ca88ab3..731a33b` | 通过。五处生产调用改为相对 API 根路径，登出仍带当前 access token。审查 `87ec145d-f89e-4330-85ab-f973d546361d`。 |

两次加载约 150KB 整段 diff 的审查在写出报告前连接中断，没有结论。本次验证因此只复核上次已完成审查之后的提交。

## 命令证据

| 命令 | 工作目录 | 退出码 | 结果 |
| --- | --- | --- | --- |
| `npm test` | `frontend` | 0 | 62 项通过，0 项失败 |
| `npm run lint` | `frontend` | 0 | ESLint 无报告 |
| `npm run build` | `frontend` | 0 | `tsc -b` 通过，Vite 产出登录页与注册页代码块 |
| `comet classic openspec -- validate frontend-auth-session --type change --strict` | 仓库根 | 0 | change valid |

生产构建包含 `LoginPage-iywVGFYq.js` 与 `RegisterPage-BKhaPuTq.js`。

## 完整性

`openspec/changes/frontend-auth-session/tasks.md` 的 12 项全部为 `[x]`。OpenSpec 进度为 12/12。

| 规格场景 | 证据 |
| --- | --- |
| 注册成功后进入登录页且不建立会话 | `RegisterPage` 成功后导航到 `/login`，不写 token |
| 确认密码不一致时不发请求 | `registerForm` 拒绝不一致密码 |
| 用户名或邮箱已被占用 | 409 显示「用户名或邮箱不可用」，保留非密码字段 |
| 记住我与不记住我 | `writeSession` 只写一种存储并清掉另一种 |
| 密码错误留在登录页 | 登录 401 显示「登录失败」，不保存会话 |
| 回到站内原地址，拒绝外部网址 | `sanitizeReturnPath` 只接受单个 `/` 开头的路径 |
| 受保护请求带 Bearer | HTTP 测试「受保护请求带 Bearer」 |
| 过期后只刷新一次并重试 | 并发 401 与窗口内刷新测试 |
| 刷新失败进入登录页 | 刷新失败时 `clearSession`，布局登出路径进入 `/login` |
| 登出带当前 access token | 登出测试断言 Bearer；401 时刷新一次再重试一次 |
| 撤销失败仍清除本地会话 | store 测试「撤销失败仍然清除会话」 |
| 导航显示用户名 | 登录后读取 `/users/me`，导航显示 `username` 或「已登录」 |
| 窄屏登录与注册入口 | `AuthLayout` 在窄屏用 `flex-wrap` 保留入口 |
| 未登录打开六个页面进入登录页 | `RequireSession` 重定向到 `/login` |
| 已登录打开未知路径显示仪表盘 | 受保护树内未知路径回到 `/` |
| 最终地址只含一段 `/api/v1` | `axios.getUri` 测试覆盖刷新、登录、当前用户和登出 |

## 正确性

生产调用路径是 `/auth/login`、`/auth/register`、`/auth/refresh`、`/auth/logout`、`/users/me`。`VITE_API_BASE_URL` 在开发环境为 `http://localhost:8000/api/v1`，在生产环境为 `/api/v1`。环境文件未改。

登录、注册和刷新不附带 access token，也不进入自动刷新。登出附带当前 access token。状态码大于等于 500 时错误消息为「服务暂时不可用」。登录、登出和注册共用一个懒创建的 HTTP 客户端。

没有新增 npm 依赖，没有解析 JWT，没有把 token 写入 cookie 或 URL。

## 一致性

`openspec/changes/frontend-auth-session/design.md` 与 `docs/superpowers/specs/2026-10-17-frontend-auth-session-design.md` 都要求相对 API 根路径、登出携带访问令牌，以及登录、注册、刷新不带 token。增量规格没有被设计文档漏掉的行为。`tasks.md` 2.1 的原句仍把登出写成不刷新；6.1 和设计文档已经覆盖登出刷新一次的行为，不构成规格与设计文档的矛盾。

## 问题

- CRITICAL：无
- WARNING：无
- SUGGESTION：注册页 `/auth/register` 没有 `axios.getUri` 测试，源码已是相对路径。邮箱校验接受点不在域名中的地址，服务端会拒绝。回跳查询串里的 `://` 会使整段地址回到 `/`。登出进行中的刷新可能在清除之后写回会话。这些都不进入本次修复。

## 最终评估

没有关键问题。可以归档。归档仍需单独确认，本报告不执行归档。
