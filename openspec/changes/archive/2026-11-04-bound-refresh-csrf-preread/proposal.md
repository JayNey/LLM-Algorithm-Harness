## Why

Issue #342：refresh 的 CSRF 预读位于认证请求体边界外，伪造 cookie 即可触发无限缓存和等待，绕过既有 16KiB 限制。

## What Changes

- 在实际预读器中逐块执行累计大小限制，超限立即 413，不再接收后续分块。
- 整次预读限定为 10 秒，超时返回 408，断连直接结束。
- 保持显式 JSON token 优先、cookie 刷新和 CSRF 拒绝语义；通过真实应用装配回归验证。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/error-handling`：补充 refresh CSRF 预读边界的提前拒绝场景。

## Impact

仅涉及 api/auth/csrf.py 和认证回归测试，无新增依赖或公开 API。
