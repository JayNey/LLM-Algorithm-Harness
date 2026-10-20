## 修复方案

在现有 HttpOnly 会话 cookie 之外增加双提交 CSRF，并在展示用户可控文本前做 HTML 转义。Bearer 客户端继续只使用 `Authorization`，不要求 CSRF 头。

### CSRF

Cookie `harness_csrf`：

- Path=`/`，HttpOnly 关闭，SameSite=`Lax`。脚本需要读取或保存响应头中的同一令牌；访问令牌 cookie 仍然是 HttpOnly。
- `Secure` 仅在请求 scheme 为 `https` 时开启。
- 登录和刷新生成新的 `secrets.token_urlsafe(32)`。`remember` 或已有 `harness_persist` 时，Max-Age 与刷新令牌相同；否则为会话 cookie。
- 登出删除该 cookie。
- 响应同时设置 `X-CSRF-Token`。CORS 暴露这个响应头，供开发环境的跨源前端读取。已有 CSRF cookie 的成功响应也回传该头，便于页面刷新后补齐本地标记。

校验：

- 仅对 `/api/v1/` 下的 POST、PUT、PATCH、DELETE。
- 请求有 `Authorization` 头时跳过，无效 Bearer 仍不得回退到 cookie。
- 没有 `Authorization`，且存在 `harness_access_token` 或 `harness_refresh_token` 时，`X-CSRF-Token` 必须与 `harness_csrf` 完全一致，使用固定时间比较。缺失或不一致返回 403，正文不包含令牌值。
- 注册和登录此时还没有会话 cookie，不因 CSRF 被拒绝。刷新和登出带有会话 cookie，必须校验。

前端：

- 会话标记增加可选 `csrfToken`。它不是访问令牌；旧的带 `accessToken` 或 `refreshToken` 的存储仍然拒绝恢复。
- HTTP 客户端在 POST、PUT、PATCH、DELETE 上附带已保存的 `X-CSRF-Token`，并从响应头更新令牌。
- 登录写入的会话包含这次响应里的令牌。刷新后的会话保留或更新该令牌，不能在刷新成功时把令牌丢掉。

### XSS

`escapeHtml` 转义 `& < > " ' /`。欢迎语、顶栏用户名、密钥列表中的名称和掩码，以及从响应 `detail`、`message`、字段错误复制出的文案，都先经过该函数。表单输入框继续绑定原始值，避免把实体再次显示进编辑框。

密钥名称仍为 1–100 字符，同时客户端和服务端拒绝 `< > & " '`。已保存的旧名称只在展示时转义，不在列表接口里改写。

## 不改动的行为

- JSON 仍返回访问令牌和刷新令牌，供非浏览器客户端使用。
- 显式 Bearer 或刷新 JSON 优先于 cookie。
- 查询参数中的令牌不能认证。
- Web Storage 不保存访问令牌或刷新令牌。
