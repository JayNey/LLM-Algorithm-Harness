## 修复任务

- [x] 1. 补充认证注入、真实任务认证执行与所有权拒绝回归并记录 RED 证据。
- [x] 2. 按实验任务模式注入认证服务并释放数据库连接，确认回归转绿。
- [x] 3. 运行相关测试、格式与编译检查，记录根因消除及验证证据。

## GREEN 与根因消除证据

- 基准任务测试：`MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py --no-cov`，13 passed。
- 相关测试：`MPLCONFIGDIR=/private/tmp/celery-benchmark-mpl pytest tests/test_benchmark_task.py tests/test_experiment_task.py tests/test_api_experiment_benchmark.py tests/benchmark --no-cov`，85 passed，5 条既有 Pydantic 弃用告警。
- `black --check src/tasks/benchmark.py tests/test_benchmark_task.py`、`ruff check src/tasks/benchmark.py tests/test_benchmark_task.py`、`python3 -m compileall -q src/tasks/benchmark.py` 与 `git diff --check` 全部退出 0。
- `comet classic openspec -- validate fix-celery-benchmark-auth --strict` 通过。
- 源码检查确认 worker 已使用 `BenchmarkService(auth=AuthService(AuthSettings()), recover=False)`，无原先直接执行的未注入构造；真实认证回归确认合法密钥完成并记录指标，外用户密钥仍失败。
- 测试在进程内执行真实 Celery 任务体、认证库和业务库，替换最终执行器；未运行 Redis broker、独立 worker、真实模型提供商或 Docker 沙箱。
