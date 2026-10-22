## 修复与验证

- [x] 1. 新增恢复状态矩阵和实验 worker 跨 API 重启完成回归，运行并记录 RED 证据。
- [x] 2. 修复三个服务的活跃任务保护条件，确认回归转绿、相关测试和格式检查通过。
- [x] 3. 检查根因消除，完成构建验证与规格核对，并提交本次修复。

## RED 证据

实现修改前运行 `python3 -m pytest tests/test_api_restart_worker_recovery.py --no-cov -q --tb=short`：退出码 1，12 failed、43 passed。失败为三个服务错误清理 `running` 记录、实验/基准不保护异步暂停到业务回写之间的记录，以及实验 worker 在 API 重启后返回 `failed` 而非 `completed`。完整日志暂存于 `/tmp/api-restart-worker-red.log`。

## GREEN 与根因消除证据

相同回归命令在修复后退出码 0：55 passed。新增的实验场景通过真实数据库、Celery 任务函数和新 API lifespan 复现重启时序，最终通过 HTTP 结果接口查询成功，并验证产物目录、完成时间和两层完成状态。

三个 `_recover_interrupted` 已不再以业务记录必须为 `pending` 作为保护活跃异步任务的条件；实验和基准查询也覆盖 `paused`。无活跃任务的 `pending/running` 记录依然失败，终态与暂停记录及已有错误信息不变。未修改 worker 的收尾守卫。

构建命令 `python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/api-restart-worker-wheel .` 成功。`compileall`、修改文件的 Ruff/Black、`git diff --check` 和 `comet classic openspec -- validate fix-api-restart-worker-recovery --strict` 均通过。

全量离线测试 `python3 -m pytest -m 'not online'`：退出码 0，2933 passed、7 skipped，覆盖率 91.78%（门槛 90%），用时 330.49 秒。完整日志暂存于 `/tmp/api-restart-worker-suite.log`。
