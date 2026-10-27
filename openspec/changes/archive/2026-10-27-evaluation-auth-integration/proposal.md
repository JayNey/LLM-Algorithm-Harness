## Why

Issue #230 要求为已经接通的评估流程补齐认证与完整离线集成证据。已有 HTTP 测试以 Bearer 为主，浏览器 security 场景主要覆盖创建 store 生命周期，尚不能证明 Cookie/CSRF 与共享刷新边界。

## What Changes

- 扩展已有离线 HTTP fixture，使用真实 Cookie 认证和 CSRF 中间件覆盖创建、启动、运行观察、结果、取消、403 与跨用户 404。
- 扩展浏览器 security/all 场景，验证真实共享 HTTP 客户端的并发 401 刷新、失败回跳及旧身份迟到隔离。
- 校正 shell fixture 的 Mock 区域请求断言，保存 JSON、截图和可复现命令及验证层级。

## Capabilities

### New Capabilities

无；本次为已有公开契约补充测试及证据。

### Modified Capabilities

无；不改变产品需求，使用 skip_specs: true。

## Impact

主要涉及 Issue 指定的 HTTP 测试、verify-evaluations.mjs、verify-shell.mjs 与验收报告；只在测试暴露明确契约缺陷时最小修复。不新增 API、schema 或外部服务。基线为 origin/main f507b568caf21abd7e325a88a7851afce5a37a03，包含前置 #229 / PR #282。
