## 问题

Issue #161 要求认证界面具备 CSRF 防护和 XSS 输入转义。当前浏览器会话已经把访问令牌和刷新令牌放在 HttpOnly、SameSite=Lax 的 cookie 里，但变更请求没有第二份 CSRF 令牌。密钥名称接受 `<`、`>`、`&`、`"`、`'`，欢迎语、顶栏用户名、密钥名称、掩码和接口错误文案也按原始字符串进入界面。

## 根因

`auth-token-httponly-cookie` 认为跨站请求不会带上 SameSite=Lax cookie，因此登录和刷新只设置会话 cookie，不签发 CSRF 令牌，服务端也不校验 `X-CSRF-Token`。同源或后续放宽 SameSite 时，只带 cookie 的 POST、PUT、PATCH、DELETE 会直接执行。

前端没有统一的 HTML 转义。展示路径把服务端文案和用户可控名称原样放进界面字符串；`key_name` 只限制长度，不拒绝 HTML 元字符。

## 修复目标

- 登录和刷新设置非 HttpOnly 的 `harness_csrf` cookie，并在响应头给出 `X-CSRF-Token`。登出时删除该 cookie。
- 没有 `Authorization` 头、但带有访问令牌或刷新令牌 cookie 的 POST、PUT、PATCH、DELETE 必须携带与 cookie 一致的 `X-CSRF-Token`，否则 403。带 `Authorization` 的请求保持原有 Bearer 行为，不校验 CSRF。
- 浏览器把 CSRF 令牌和现有会话标记一起保存，变更请求附带该头。令牌不得替代访问令牌，也不得写入访问令牌字段。
- 欢迎语、顶栏用户名、密钥名称、掩码和接口错误文案经过 HTML 转义后再展示。新的密钥名称在客户端和服务端都拒绝 HTML 元字符。
- 已有 Bearer 测试和查询参数拒绝行为保持不变。

用户已确认这超出 hotfix 的常规范围（跨模块、认证契约会变，改动文件数超过提示阈值），并选择继续 hotfix，在分支 `hotfix/20261020/auth-csrf-xss` 上实现。
