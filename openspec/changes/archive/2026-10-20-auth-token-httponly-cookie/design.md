## 修复方案

登录和刷新在保留现有 JSON 令牌字段的同时设置 cookie，供非浏览器客户端继续使用 Bearer。浏览器只依赖 cookie。

Cookie：

- `harness_access_token`：Path=`/api`，HttpOnly，SameSite=`Lax`。覆盖 `/api/v1` 的普通请求和 WebSocket。
- `harness_refresh_token`：Path=`/api/v1/auth`，HttpOnly，SameSite=`Lax`。只随刷新和登出发送。
- `harness_persist`：Path=`/api`，HttpOnly，值为 `1`。只表示“记住我”，不含令牌。
- `Secure` 仅在请求 scheme 为 `https` 时开启，本地 HTTP 和测试客户端可以保存 cookie。
- 登录体增加可选字段 `remember`，默认 `false`。为真时 cookie 带 Max-Age：访问令牌用 `expires_in`，刷新令牌和 persist 用刷新寿命。为假时使用浏览器会话 cookie。刷新时若请求带有 persist cookie，则继续设置 Max-Age。
- 登出删除这三个 cookie，并继续撤销服务端会话。

认证顺序：

- 请求带有 Authorization 头时只解析 Bearer。头无效则 401，不读取 cookie。
- 没有 Authorization 头时读取访问令牌 cookie。
- 刷新体里有 `refresh_token` 时只用该字段。没有时读取刷新 cookie。
- URL 查询参数中的令牌继续忽略。WebSocket 仍接受现有 `token` 查询参数；参数为空时改读访问令牌 cookie。

跨站请求不携带 SameSite=Lax cookie，因此不为这次修复另加 CSRF 令牌。CORS 改为 `allow_credentials=true`，origin 仍使用现有明确白名单，不能改成 `*`。

前端：

- axios 使用 `withCredentials`。
- Web Storage 只保存非秘密会话标记：随机 `marker`、`expiresAt`、`username`。记住我仍决定写入 `localStorage` 还是 `sessionStorage`。
- 登录请求带上 `remember`。响应只使用 `expires_in` 计算过期时间，不把 JSON 中的令牌写入存储或请求头。
- 刷新发送空 JSON 对象，由浏览器附带刷新 cookie。并发刷新仍共用一次请求，并用 `marker` 判断会话是否已被登出或重新登录替换。

测试客户端会自动保存 Set-Cookie。返回 Bearer 令牌的测试登录助手在取到 JSON 后清空 cookie jar，避免随后“无 Authorization 应返回 401”的断言被 cookie 误认证。专门的 cookie 测试保留 jar。
