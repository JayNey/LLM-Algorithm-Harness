# 构建与回归证据

- 分支：tweak/20261026/ab-test-async；基线：33cff8d。
- 完整 pytest：3347 passed、11 skipped、覆盖率 92.44%。该次执行开始后追加了 PostgreSQL 未命中 CAS 和执行 attempt 归属两项边界修复。
- 上述最终修复及新增 Request 上下文、失败信号权限回归之后，所有受影响范围重跑：230 passed。命令：pytest tests/test_ab_test_task.py tests/test_utf8_io.py tests/test_async_task_submission.py tests/test_task_manager.py tests/test_api_experiment_benchmark.py tests/test_execution_logs.py tests/test_api_monitoring_task_snapshots.py tests/test_api_monitoring_service.py tests/test_ab_testing.py -q -o addopts=''。
- 前端 npm test：257 passed；npm run build：通过；npm run lint：0 error，2 个已有 BenchmarkDetailPage hook 警告。
- ruff check .、black --check .、python3 -m compileall -q api src、git diff --check：通过。
- 核心 4 文件 mypy（follow-imports=silent）：通过。全量 mypy 的 5 个错误已在 33cff8d 独立基线副本复现，位于 parsing.py、cost_service.py、progress.py、cost_alert_service.py，属于既有问题。
- OpenSpec strict validate：通过。
- 只读集成审查及同次修复复核：无剩余 Important；发布并发、初始化失败、真实父进程 WorkerLostError、attempt 归属均有回归。
- 使用隔离临时数据库在浏览器验证排队页面：显示等待提示、不显示启动按钮、删除按钮禁用。
- 未连接生产 Redis 或模型提供商；外部 broker/backend/模型调用由测试替身隔离，使用真实临时 SQLAlchemy 数据库、Celery trace 和父进程 Request.on_failure 验证生命周期。
