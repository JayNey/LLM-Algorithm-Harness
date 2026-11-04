## 1. 修复与回归

- [x] 1.1 补充真实应用 ASGI 边界回归，观察失败后实现累计 16KiB 限制、总读取时限及断连处理，验证刷新和 CSRF 语义。

## 2. 验证

- [x] 2.1 执行相关认证和错误契约测试、完整离线测试及格式/静态检查，记录验收证据。

## 验收证据

- RED：真实应用 ASGI 回归 7 failed / 3 passed，复现无头 403、超限后继续读取、无总时限、断连后继续响应。
- GREEN：认证测试 79 passed；补充合法显式 token 优先用例后，定向认证测试 12 passed；统一错误契约 30 passed。
- 完整离线套件：3803 passed / 18 skipped / 18 errors / 1 failed，覆盖率 92.96%（门槛 90%）。19 个异常均为 socket.bind 的 PermissionError（沙箱禁止本地端口），具体为成本 HTTP 4 项、nginx 就绪 14 项、broker 1 项。
- 上述异常在允许本地回环端口后定向重跑：成本 4 passed，nginx/broker 15 passed。未修改其他模块源码。
- ruff 全仓通过；black 全仓 381 文件通过；compileall api/src 通过；mypy api/auth/csrf.py 通过；wheel 构建成功；OpenSpec strict 校验通过。
- 日志位于 /private/tmp/issue-342-{pytest,socket-retest,runtime-retest,auth-check,errors}.log；存在既有 Pydantic 等弃用警告。
