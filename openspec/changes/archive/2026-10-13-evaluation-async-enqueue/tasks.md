## 1. 入队时序（先落库后发布）

- [x] 1.1 在 `TaskManager` 新增 `enqueue_task(...)`：预生成 `celery_task_id`、创建并 `commit` AsyncTask（含 `on_before_publish` 钩子）后再 `send_task(task_id=...)`；send 失败时置该 AsyncTask 为 failed 并抛出。`create_task` 行为不变
- [x] 1.2 单元测试覆盖：关联在发布前已落库、发布使用预生成 id、send 失败时任务置 failed

## 2. 评估启动接口接入 Celery

- [x] 2.1 `start_evaluation` 用 `enqueue_task` 提交 `run_evaluation_task` 并在发布前设置 `evaluation.async_task_id`；评估保持 `pending`、不再开线程，返回评估视图。用 API/服务测试验证不依赖进程内线程
- [x] 2.2 移除 `_run_simulated`/`_execute_task` 及仅服务模拟的私有辅助，清理不再使用的导入
- [x] 2.3 `create_evaluation_async` 改用 `enqueue_task` 修复入队时序，保持既有语义

## 3. 取消与重启恢复

- [x] 3.1 `cancel_evaluation` 在有关联任务时经 `TaskManager.cancel_task` revoke Celery 再置评估 `cancelled`；无关联任务维持原行为
- [x] 3.2 `_recover_interrupted` 保留已入队 `pending` 评估；无关联 `pending` 与 `running` 仍标中断

## 4. 测试与回归

- [x] 4.1 调整 `test_api_database.py`（start 后为 `pending` 而非 `running`）、`test_api_auth.py::test_owner_evaluation_lifecycle` 与 `test_evaluation_service_async.py`
- [x] 4.2 运行评估/任务相关测试与 ruff/mypy，全部通过
