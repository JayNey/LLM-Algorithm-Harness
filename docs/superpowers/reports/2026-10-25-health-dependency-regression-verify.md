# 健康检查故障恢复回归验证

- Change：health-dependency-regression
- 分支：codex/health-dependency-regression
- 实现提交：ec4ccaf
- 结论：PASS

## 范围与证据

仅修改 tests/test_api_readiness.py 及当前 change 文档/Comet 元数据。真实 lifespan 测试分别临时破坏认证表、文件表、业务表与迁移记录，在同一应用和 checker 上验证正常→故障→恢复；finally 恢复数据库。每阶段验证存活为 200、就绪为 200/503/200、最小 JSON 与 no-store。可选 Redis、worker、沙箱禁止参与探测。

新增 HTTP 探测异常用例采用默认一秒缓存，以模块局部可控时钟推进缓存过期，验证成功缓存、异常转为 503、失败缓存和自动重新探测恢复；不重建应用、不清空缓存、不修改全局或 asyncio 时钟。

验证命令与结果：

- `pytest tests/test_api_readiness.py --no-cov -q`：26 passed。
- `pytest tests/test_api_readiness.py tests/test_api_monitoring.py tests/test_api_documentation.py tests/unit/test_api_endpoints.py --no-cov -q`：942 passed，59.00s；19 项现有 Pydantic/SQLAlchemy 弃用警告。
- `python3 -m compileall -q api tests/test_api_readiness.py`：通过，verify 阶段重新执行。
- `black --check tests/test_api_readiness.py`、`ruff check tests/test_api_readiness.py`、`git diff --check`：通过。
- `comet classic openspec -- validate health-dependency-regression --strict`：通过，skip_specs，无行为变更。

变异验证：在独立 Python 进程包装 ReadinessCheck.check，令第一次失败后永久返回 False。5 个恢复场景全部在最后应为 200 的恢复断言失败（实际 503），证明可识别故障后无法恢复的回归。变异不写入源码；原实现随后完成上述 942 项通过验证。

## 轻量验证六项

1. tasks 全部完成：PASS，1/1。
2. 改动符合任务范围：PASS，1 个测试文件及当前 change 产物。
3. 编译：PASS，compileall。
4. 相关测试：PASS，942 项；此次未运行全仓测试或全仓覆盖率门槛。
5. 安全：PASS，使用临时数据库，无生产数据修改；异常详情不会进入公共 JSON。
6. 最终自动代码审查：按本 change 初始化的 review_mode=off 跳过；已核对最终 diff 和任务要求。

规模工具因计入 Comet 快照和状态文件统计 13 个文件。实际实现仅 1 个测试文件、1 个任务、0 个 delta spec，按 comet-verify 的覆盖机制采用 light。未提交改动均为验证阶段报告和状态记录；branch_status 保持 pending，等待归档确认。
