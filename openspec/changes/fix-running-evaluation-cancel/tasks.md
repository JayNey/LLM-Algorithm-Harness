## 1. 运行中评估的协作式取消

- [x] 1.1 `TaskManager.cancel_task` 对 `evaluation` 任务用与 worker 相同的 `data/tasks/{evaluation_id}` 和 `eval-{evaluation_id}` 调用 `TaskService.request_cancel`；检查点不存在时忽略并继续 revoke，数据库状态仍为 `cancelled`。验证：`python3 -m pytest tests/test_task_manager.py -q --no-cov` 中新增用例通过，断言检查点 `cancel_requested` 为真，且无检查点时取消仍成功。

- [ ] 1.2 `run_evaluation_task` 在执行前发现任务已是 `cancelled` 时直接返回；`run()` 结束后重新读取任务，若已是 `cancelled`，评估保持 `cancelled`，不用检查点的完成、暂停或失败状态覆盖。验证：`python3 -m pytest tests/test_celery_tasks.py -q --no-cov` 中新增用例通过，断言仍有未派发单元时取消后状态为 `cancelled`，且已执行单元数小于总数。

## 2. 真实 worker 集成测试

- [ ] 2.1 为完成用例增加测试专用 Celery 入口：导入真实应用后，在 worker 进程内替换凭证解析、策略 runtime 预检、题目执行和成本估算。种子评估写入 `model`、`api_key_id` 和可解析题目，断言任务与评估变为 `completed`，且 `completed_count` 等于题目数。验证：有 Redis 时 `python3 -m pytest tests/test_async_task_integration.py -q --no-cov -o addopts=` 通过；无 Redis 时该模块跳过且不报错。
