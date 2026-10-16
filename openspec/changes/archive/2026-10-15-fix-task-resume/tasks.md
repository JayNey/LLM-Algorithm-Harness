## 1. 恢复实现

- [x] 1.1 在 `TaskManager` 增加 `resume_task`：仅允许调用方自己的 `paused` 评估任务；生成新的 `celery_task_id`，把任务和关联评估写成 `pending` 并先提交，再发布 `src.tasks.evaluation.run_evaluation_task`；发布失败时把任务标为 `failed`。非暂停、非评估、未知类型或不属于调用方时拒绝，且不发布消息、不改原记录。验证：`python3 -m pytest tests/test_task_manager.py -q --no-cov` 中新增用例通过。

- [x] 1.2 让 `POST /api/v1/tasks/{task_id}/resume` 调用 `resume_task`，不再读取不存在的字段。验证：`python3 -m pytest tests/test_tasks_api.py tests/test_evaluation_async_flow.py -q --no-cov` 通过，且恢复用例断言同一任务标识、`pending` 状态，以及非法恢复不发布消息。
