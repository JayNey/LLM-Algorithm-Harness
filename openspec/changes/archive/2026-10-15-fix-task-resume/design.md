## Context

见 `proposal.md`。`AsyncTask` 只有 `task_type`、`entity_id`、`user_id` 和 `celery_task_id`，没有保存 Celery 任务名或参数。评估 worker 通过 `evaluation.async_task_id` 找到任务，并用 `TaskService` 里状态为 `paused` 或 `failed` 的检查点继续执行。实验、导入和基准 worker 用 `(task_type, entity_id, user_id)` 取第一条记录，且只接受业务状态为 `pending` 的启动。

## Goals / Non-Goals

**Goals:**

- 恢复接口对暂停的评估任务返回原来的任务标识，状态为 `pending`。
- 新的 Celery 消息在数据库提交之后发布。
- 非法恢复不改记录、不发布消息。

**Non-Goals:**

- 不让实验、导入、基准支持暂停或恢复。
- 不新增列，不改评估以外的入队时序。
- 不改 `EvaluationService.resume_evaluation` 的现有行为。

## Decisions

1. **沿用同一条 `AsyncTask`，不新建记录。** 新建记录会让 `owned_async_task()` 的 `.first()` 命中不确定，也要改评估外键。同一条记录换新的 `celery_task_id` 后，评估关联保持有效，worker 仍能读到 `TaskService` 检查点。备选是持久化任务名和参数再新建记录，那需要加列，本次不采用。

2. **只恢复 `task_type == "evaluation"`。** Celery 任务固定为 `src.tasks.evaluation.run_evaluation_task`，参数为 `(entity_id,)`。其他类型即使被标成 `paused`，worker 也不会从检查点继续，重新入队可能把仍在运行的业务记录标失败。这些请求返回 400。备选是按类型推导全部任务签名并一律入队，风险大于收益。

3. **先落库再发布。** 生成新的 `celery_task_id`，把任务和关联评估都写成 `pending`，提交后再 `send_task(..., task_id=celery_task_id)`。发布失败时把该任务标为 `failed` 并写上错误信息。这与评估启动已有的 `enqueue_task()` 顺序一致。

4. **恢复逻辑放在 `TaskManager.resume_task`。** 路由只负责调用和把 `ValueError` 转成 400/404。不走现在的 `create_task()`。

## Risks / Trade-offs

- [旧 worker 尚未观察到暂停时又收到恢复] → 与现有 `resume_evaluation` 相同，本次不新增锁。调用方应在任务已经停在 `paused` 之后再恢复。
- [非评估暂停任务被拒绝] → 接口不再 500，但这些类型的暂停仍只是状态标记。那是另一项工作，不在本次范围。

## Migration Plan

无数据迁移。回滚时恢复路由重新抛出错误即可，已重新入队的任务仍由现有 worker 执行。
