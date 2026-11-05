# refresh CSRF 预读边界验证

结论：PASS。change `bound-refresh-csrf-preread`，对应 issue #342。验证采用 full，任务 2/2 完成，delta requirement 与实现、设计一致；无待解决 CRITICAL/IMPORTANT 或规格漂移。

## 实现和场景覆盖

- `api/auth/csrf.py` 在超限块追加前检查累计 16384 字节，立即返回统一 413；后续 receive 不再消费。缓冲跳过空分块，避免空分块增加列表内存。
- 采用单调时钟截止时间及每次 receive 的剩余超时，覆盖空分块持续滴流和停滞读取，返回统一 408。断连直接退出，不再回放或调用下游。
- `tests/test_api_auth.py` 通过真实 create_app 装配覆盖：有/无 CSRF 头、首块/累计超限、精确上限、慢/持续读取、断连；验证错误码、no-store、CORS 和请求 ID。
- 既有 cookie 刷新与 403 测试通过；显式有效 JSON token 在假 cookie、无 CSRF 头条件下刷新成功，保留 token 优先语义。
- delta 中原有凭证、上传和 CORS 场景由现有认证及错误契约测试覆盖。无公开 API、依赖、数据库或中间件顺序变更。

## 实测证据

- RED：新增 ASGI 测试在原代码上 7 failed / 3 passed，确认失败对应超限、读取时限和断连缺失。
- GREEN：认证测试 79 passed；新增合法显式 token 用例后定向认证 12 passed；统一错误契约 30 passed。
- `python3 -m pytest -m 'not online'`：3803 passed、18 skipped、18 errors、1 failed，耗时 573.76 秒。全部 19 项异常为沙箱拒绝 socket.bind 的 PermissionError。覆盖率 92.96%，超过 90% 门槛；未将首次完整运行描述为零失败。
- 允许本地回环端口后重跑全部 19 项：成本 HTTP 4 passed；部署就绪 14 项及 broker 1 项共 15 passed。最终没有未解决的测试失败。
- 全仓 ruff 和 black（381 文件）、api/src compileall、csrf.py mypy、wheel 构建、OpenSpec strict 校验及 git diff --check 均通过。
- 存在既有 Pydantic 等弃用警告。未调用真实模型服务。测试产生的 20 个空 execution lock 已核对并清理。

原始日志：`/private/tmp/issue-342-pytest.log`、`/private/tmp/issue-342-socket-retest.log`、`/private/tmp/issue-342-runtime-retest.log`、`/private/tmp/issue-342-auth-check.log`、`/private/tmp/issue-342-errors.log`。

## 一致性与审查

proposal 目标均满足；design 的逐块限制、总截止时间和单次回放均已实现。tweak 不要求额外 Superpowers Design Doc/plan。本次状态的 review_mode 为 off，因此跳过自动代码审查；最终 diff 人工核对未发现新增安全或边界问题。主 spec 将在用户确认归档后按 delta 合并。

当前分支 `comet/bound-refresh-csrf-preread`；实现及构建证据已提交，验证阶段新增内容仅为此报告和 Comet 状态。

## 归档交付授权

用户选择 C：确认归档、提交、推送当前绑定分支并创建关联 #342 的 PR。按此方式执行归档与交付，不合并 PR。

## 2026-11-05 CI 修复

PR #346 的首次 CI 在 Windows 3.11/3.12 中分别出现 29/28 项失败，均来自此前已有的测试隔离问题：

- Windows fixture 用数值等于 5 判断默认超时，将测试显式传入的 5 秒也改为 15 秒，导致模拟 6 秒调用的 28 项超时断言失效。改为通过 Pydantic model_fields_set 判断字段是否显式设置，保留未指定超时的 Windows 默认扩展。
- 并发恢复测试只模拟 send_task；较晚进入的竞争者看见 pending 后会读取真实 Redis。补充 PENDING 结果替身，新增 late_competitor 参数，稳定覆盖首次恢复完成后才读取的场景，仍断言恰好一次成功及一次发布。

本地通过临时 pytest 插件，仅将 Windows fixture 自身的 platform 输入设为 win32：原代码 28 failed，修改后 28 passed。业务恢复测试完整文件 91 passed；改动文件 black、ruff、git diff --check 通过。应用与沙箱业务源码未改动。完整离线回归和推送后的 CI 继续验证。
