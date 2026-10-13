## Context

`run_evaluation_task`（`src/tasks/evaluation.py`）已是完整 Celery 任务：用 TaskService 执行、回写 AsyncTask 与 Evaluation 状态，并通过 `evaluation.async_task_id` 解析关联任务；其 `worker()` 仍是占位 mock（真实执行体另开 change）。产品侧 `POST /evaluations/{id}/start` 走 `EvaluationService.start_evaluation`，用 `threading.Thread` + `_run_simulated` 在 API 进程内模拟；`create_evaluation_async` 会入队但未接任何路由，且先 `send_task` 后提交关联，存在竞态。#181 已为实验/导入/基准建立“启动接口只入队、worker 置 running、重启保留已入队 pending”的模式。

## Goals / Non-Goals

**Goals:**

- 评估启动接口提交 `run_evaluation_task`，评估保持 `pending` 直到 worker 执行。
- 入队“先落库后发布”，消除 worker 读不到关联任务的竞态。
- 取消评估时 revoke 对应 Celery 任务。
- 重启不把已入队 `pending` 评估标失败。

**Non-Goals:**

- 不实现真实评估执行体（`worker()` 仍为 mock），另开完整 change。
- 不改 `run_evaluation_task` 的执行/进度/暂停逻辑与任务签名。
- 不改数据库结构，不动 `create_task` 既有行为（避免影响 #181 的实验/导入/基准）。
- 不接 ab_test（属 #156）。

## Decisions

1. 新增 `TaskManager.enqueue_task(...)`：预生成 `celery_task_id=uuid4`，创建 AsyncTask（status=pending）并 flush，调用可选 `on_before_publish(async_task)` 钩子（评估用它设置 `evaluation.async_task_id`），`commit` 落库后再 `celery_app.send_task(name, args, kwargs, task_id=celery_task_id)` 发布；发布失败则把 AsyncTask 置 failed 并 commit 后抛出。`create_task` 保持不变。
2. `start_evaluation`：校验 `pending` → 用 `enqueue_task` 提交 `run_evaluation_task`（args=(evaluation_id,)），`on_before_publish` 设置关联；不再置 running、不再开线程；返回评估视图。`running` 由 worker 设置。
3. `cancel_evaluation`：若 `evaluation.async_task_id` 存在，调用 `TaskManager.cancel_task` revoke 并置 AsyncTask cancelled，再把评估置 cancelled；无关联任务时维持原有直接置 cancelled 行为。
4. `_recover_interrupted`：只把“无关联 AsyncTask 的 pending”与“running 且其关联任务非 pending/running”的评估标失败；已入队 pending 评估保留（对齐 #181 决策 3）。
5. `create_evaluation_async`：改用 `enqueue_task` 修复其入队时序，保持既有语义与测试。
6. 移除 `_run_simulated`/`_execute_task` 及仅服务于模拟的私有辅助（`_record_tick`/`_status_of`/`_spent_of`/`_finish`/`_fail`），并清理不再使用的 `threading`/`time`/`Semaphore` 导入。

## 继续 tweak 的确认

用户已在入口选择“②③ 走 tweak、① 真实执行体另开 full”，并确认本次范围为仅评估、隔离为新建分支。触发提示的是改动跨 `TaskManager` 与 `evaluation_service` 且波及多个测试文件。确认原因：只把评估启动接口改成提交已有 Celery 任务并修正入队时序，不新增任务类型、不改数据库结构、不改 `run_evaluation_task` 执行逻辑。

## Risks / Trade-offs

- [测试等待进程内线程跑完] → start/cancel 测试改为断言任务标识与 `pending`/`cancelled`；需要执行结果的用例直接调用 `run_evaluation_task` 或 mock `send_task`，不依赖 Redis。
- [先落库后发布，发布失败留下 pending AsyncTask] → `enqueue_task` 在 send 失败时把该 AsyncTask 置 failed 并抛出，调用方据此处理评估状态。
- [没有 worker 时评估停在 pending] → 与实验/基准一致，部署需启动 worker。
