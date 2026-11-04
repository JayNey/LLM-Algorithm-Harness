## 实现
新增私有调用级计时对象，由单次测试或内存分析创建，通过私有 runner 参数传入命令层。命令 finally 在清理前记录 perf_counter 耗时；调用方的成功、解析失败和后端失败均读取该对象。尚未启动命令的错误使用本次调用单调时钟耗时。移除实例共享字段，不加执行大锁，不改变 runner 输出契约。
## 验证
用 Event 控制 A 在清理暂停，B 完成后释放 A；命令时钟固定 A=0.1 秒、B=6 秒，覆盖两种输入输出模式和失败、清理异常。通过 Harness.run 默认任务调度共享 runtime 复验。真实 Docker 并发执行并确认清理预算不参与判题；执行相关沙箱、内存分析和 Harness 回归、格式及静态检查。

## 构建验证证据
- RED：原实现确定性并发回归 20 项失败；正常 A 实际为 timeout/6.0，预期 passed/0.1。
- GREEN：扩展后确定性回归 28 项通过，包括 Harness.run(use_task_service=True) 使用默认 max_workers=5 的共享 runtime 和内存分析。
- RUN_DOCKER_TESTS=1 python3 -m pytest tests/test_sandbox_docker.py --no-cov -q：50 passed（26.81s），包含真实 Docker 两种模式的并发清理等待。
- 相关七组测试：204 passed, 8 skipped（未设置 RUN_DOCKER_TESTS 的真实 Docker 用例在此组跳过，已单独全量执行）。
- black --check、ruff check、mypy src/sandbox_executor.py、compileall src 均通过。
- 既有提示：Pydantic class Config 弃用、pytest 模型类收集与 class fixture 弃用；无新增失败。
