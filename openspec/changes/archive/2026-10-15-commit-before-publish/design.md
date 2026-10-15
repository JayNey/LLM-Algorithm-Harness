## Context

见 `proposal.md`。`TaskManager.enqueue_task()` 已经预生成 `celery_task_id`，提交 `AsyncTask` 后再 `send_task(..., task_id=...)`；发布失败会把该记录标为 `failed`。评估启动使用这条路径。实验启动、题目导入、基准运行和 `POST /api/v1/tasks` 仍调用 `create_task()`，它在 `send_task` 之后才 `commit`。

## Goals / Non-Goals

**Goals:**

- 四个入口在发布前已经能从数据库读到任务记录。
- 发布使用的 `celery_task_id` 与落库记录一致。
- 发布失败后该记录为 `failed`，并带有错误信息。

**Non-Goals:**

- 不修改 `create_task()` 的既有顺序。
- 不修改 `EvaluationService.resume_evaluation`。
- 不让实验、导入、基准支持暂停或恢复，也不补它们的进度字段。

## Decisions

1. **四个入口改调 `enqueue_task()`，不改 `create_task()`。** 先落库再发布的行为已经在 `enqueue_task()` 里，包括发布失败标记。改 `create_task()` 会连带改变 `EvaluationService.resume_evaluation`，那不在本次范围。备选是让 `create_task()` 直接转调 `enqueue_task()`，影响面更大。

2. **这四个入口不使用 `on_before_publish`。** 实验记录和基准运行在入队前已经存在并保持 `pending`；导入作业也在入队前创建。worker 按 `task_type`、`entity_id`、`user_id` 查找任务，不依赖发布前再写一条业务外键。备选是像评估那样在同一事务里写关联，当前模型没有这个字段。

3. **发布失败沿用 `enqueue_task()` 的结果。** 异常原样抛出，任务状态为 `failed`，`error_message` 为 `failed to publish task to broker`。调用方不再遇到“消息已发出但记录未提交”的窗口。

## Risks / Trade-offs

- [既有测试按 `create_task()` 断言 `send_task` 不带 `task_id`] → 更新这些断言，使它们接受预生成的 `task_id`，并检查发布时记录已提交。
- [发布失败会留下 `failed` 记录] → 这是可查询的失败，而不是未提交的空事务。调用方按现有异常处理返回错误。

## Migration Plan

无数据迁移。回滚时这四个入口改回 `create_task()` 即可；已经按新顺序入队的任务仍由现有 worker 执行。
