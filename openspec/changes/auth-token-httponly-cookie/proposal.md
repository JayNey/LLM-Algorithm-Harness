## 问题

浏览器把访问令牌和刷新令牌写进 `localStorage` 或 `sessionStorage`。同源脚本可以读出这两个令牌。Issue #161 要求把令牌放进 httpOnly cookie。

## 根因

登录和刷新接口只在 JSON 里返回令牌。前端把令牌存进 Web Storage，并在请求上设置 `Authorization: Bearer`。后端只从 Bearer 头或刷新 JSON 字段读取令牌，登录响应不设置 cookie。

## 修复目标

- 登录和刷新设置 HttpOnly、SameSite=Lax 的访问令牌 cookie 和刷新令牌 cookie。
- 浏览器前端不再把令牌写入 Web Storage，也不再从脚本设置 Authorization。
- 没有 Authorization 头时，受保护请求和 WebSocket 可以使用访问令牌 cookie。
- 查询参数中的令牌仍然不能认证。
- 已有脚本和测试继续使用 JSON 中的令牌和 Authorization Bearer。显式提供的 Bearer 或刷新 JSON 优先于 cookie，无效 Bearer 不得回退到 cookie。

用户已确认这超出 hotfix 的常规范围（跨模块、认证契约和已有验收场景都会变），并选择继续 hotfix，在分支 `hotfix/20261020/auth-token-httponly-cookie` 上实现。
