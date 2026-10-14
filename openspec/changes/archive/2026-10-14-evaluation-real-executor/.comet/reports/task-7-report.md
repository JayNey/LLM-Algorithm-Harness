# Task 7 报告：resume 去重验证（evaluation-real-executor 3.2）

- **状态**：DONE_WITH_CONCERNS
- **提交哈希**：`c72741bdf7c10b0512b1d09967bbc6d41968d79b`（短 `c72741b`，父提交 `acf5730`）
- **分支**：`comet/evaluation-real-executor`
- **diff 规模**：1 file changed, 60 insertions(+), 0 deletions(-) —— 仅 `tests/test_celery_tasks.py`
- **工作区**：提交后 `git status --short` 干净；`data/tasks/` 无遗留未跟踪文件

## 0. 背景：本次是 GREEN 收尾

前一个 implementer 已完成 RED 阶段（新增测试 + 人为禁用 `src/tasks/evaluation.py`
的 resume 检测以演示失败），但在被平台中断时**尚未进入 GREEN**。本次接手：

1. 自己**实跑一次** RED（不采信前人的转述）；
2. 撤销人为演示手段（恢复 resume 检测那一行）；
3. 完成 GREEN 验证并提交。

`src/tasks/evaluation.py` 恢复后与 `acf5730` 完全一致（`git diff --stat` 为空），
因此本次提交实际只含测试文件；`git add src/tasks/evaluation.py` 是空操作。
也就是说：**resume 去重的生产实现本就已在 Task 6 到位，Task 7 的产物是证明它的测试**。

## 1. 新增测试摘要

`tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining`

场景：1 策略 × 2 题目（`p1`/`p2`，`total_units=2`）；`integration_harness.cost=0.05`
而 `budget_cap_usd=0.03` → 首单元完成后预算触顶，第一次执行以 `paused` 结束（只真实执行 1 个单元）；
随后把 `budget_cap_usd` 提到 `10.0`，再次调用 `run_evaluation_task(evaluation_id)` 走 resume。

5 类断言：

| # | 断言 | 覆盖的 3.2 要求 |
|---|------|----------------|
| 1 | 终态：`ev.status in ("completed","failed")` 且 `second_result["status"] == "completed"`；第一次执行 `ev.status == "paused"`、`first_result["status"] == "paused"` | paused→resume→completed 状态机 |
| 2 | 计数续增不重置：`ev.completed_count + ev.failed_count == total_units`、`ev.completed_count >= first_done` | `completed_count` 在既有基础上续增 |
| 3 | 无重复行：`db_session.query(EvaluationResult).count() == total_units`（每单元恰好一行，upsert 幂等） | 不产生重复 `EvaluationResult` |
| 4 | 成本续增：`ev.spent_usd >= first_spent` | `spent_usd` 在既有基础上续增 |
| 5 | 仅剩余单元执行：`len(execute_calls) == len(set(execute_calls)) == total_units` 且 `set(execute_calls) == {("vanilla","p1"), ("vanilla","p2")}`（resume 前另断言 `len(execute_calls) == 1`） | 已完成单元不重复执行（每单元经 harness 恰好执行一次） |

第 5 类断言打在真实 harness 的调用记录上（不是 mock 内部计数），直接证明 dedup 发生在
TaskService 的单元调度层（`paused` 记录里 terminal 单元保留、仅剩余 `queued` 单元被调度）。

## 2. RED 证据（第 1 步，本次亲自实跑）

命令：

```
python3 -m pytest tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining -v --no-cov
```

（此时 `src/tasks/evaluation.py:144` 为
`if False and existing_record.state in ("paused", "failed"):`）

失败输出关键行：

```
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining FAILED [100%]

_ TestRunEvaluationTaskIntegration.test_resume_after_pause_runs_only_remaining _
/Users/charlesleclerc/LLM-Algorithm-Harness/tests/test_celery_tasks.py:928: in test_resume_after_pause_runs_only_remaining
    second_result = run_evaluation_task(evaluation_id)
/Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py:150: in run_evaluation_task
    task_service.create(
/Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py:218: in create
    raise ValueError(f"Task '{identifier}' already exists")
E   ValueError: Task 'eval-4664d856-9c28-43f0-ac8f-2adbe6428ed5' already exists
=========================== short test summary info ============================
FAILED ...::test_resume_after_pause_runs_only_remaining - ValueError: Task 'eval-4664d856-9c28-43f0-ac8f-2adbe6428ed5' already exists
========================= 1 failed, 1 warning in 2.07s =========================
```

RED 结论：resume 被禁用后，第二次执行在 `if not resume:` 分支走 `task_service.create()`，
对已存在的 `run_id` 重复建记录 → `ValueError`。**注意**：失败点比任务简报预期的更早 ——
不是死在 `execute_calls`/重复行断言上，而是在进入调度前就抛错。这仍然证明测试对 resume
行为敏感（禁用即红），但对「保留 resume 检测、却破坏单元去重」这类回归，测试会改由
断言 3/5（重复行、重复执行）捕获，而非由这条 `ValueError` 路径捕获。见 §4 顾虑 3。

## 3. GREEN 证据（第 3 步）

源码改动（本次唯一允许的源码改动，撤销 RED 演示手段）：

```
-            if False and existing_record.state in ("paused", "failed"):
+            if existing_record.state in ("paused", "failed"):
```

改动后 `git diff src/tasks/evaluation.py` 为空（等同 `acf5730`），确认没有夹带任何新功能。

命令与结果：

```
$ python3 -m pytest tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining -v --no-cov
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining PASSED [100%]
========================= 1 passed, 1 warning in 1.48s =========================

$ python3 -m pytest tests/test_celery_tasks.py -q --no-cov
tests/test_celery_tasks.py .......................                       [100%]
======================== 23 passed, 1 warning in 1.47s =========================
```

额外自发的全量验证（TDD 技能要求「其他测试指项目全套，而不只是本文件」）：

```
$ python3 -m pytest -q --no-cov -p no:randomly
========== 1651 passed, 6 skipped, 113 warnings in 151.69s (0:02:31) ==========

$ python3 -m ruff check src/tasks/evaluation.py tests/test_celery_tasks.py
All checks passed!
```

无失败、无新增错误；113 warnings 全为既有告警（Pydantic V2 class-based config、
SQLAlchemy `Result.tuples()` 弃用、matplotlib legend / scipy 精度提示），与本任务无关。

## 4. 提交

```
$ git add src/tasks/evaluation.py tests/test_celery_tasks.py
$ git commit -m "test(eval): verify resume dedup and continued accumulation (evaluation-real-executor 3.2)"
c72741b test(eval): verify resume dedup and continued accumulation (evaluation-real-executor 3.2)
 tests/test_celery_tasks.py | 60 ++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 60 insertions(+)
```

## 5. 顾虑

1. **TDD「先红」的性质**：本测试验证的是 Task 6 已实现的行为（post-hoc），RED 靠人为注入
   回归（`if False and ...`）获得，而非「实现前天然失败」。这是接手被中断的 Task 7 的既定
   安排，注入手段已完整撤销，但它不等同于标准 TDD 的 RED；测试的有效性由 §3 GREEN +
   §2 注 3 的失败路径共同支撑。建议后续同类「为已有行为补证明测试」的任务在 plan 中显式
   标注为 mutation-style RED，避免被误读为绕过 Iron Law。
2. **提交只含测试文件**：`src/tasks/evaluation.py` 恢复后与 HEAD 无差异，因此 commit
   `c72741b` 是纯测试提交。若 review 环节期望看到源码 diff，需以「源码本已正确」解释。
3. **去重断言的可覆盖性有限制**：resume 检测与单元去重是两个环节。当前测试能证明
   (a) 无 resume 检测 → 立即 `ValueError`（重复建记录）；(b) 有 resume 检测 → 每单元恰好
   执行一次、结果表无重复行。若未来有人把 `TaskService.run` 改成「重新调度全部单元」，
   本测试会由 `len(execute_calls) == len(set(execute_calls)) == total_units` 与
   `EvaluationResult.count() == total_units` 变红 —— 已由 GREEN 通过的断言实际执行到了
   这条校验，覆盖成立。
4. **`ValueError` 在真实部署下的结局未验证**：RED 显示 resume 失效会抛出 `ValueError`。
   `run_evaluation_task` 外层既有 `except (ValueError, FileNotFoundError)` 会把它归为
   `failed`（不触发 autoretry，`autoretry_for` 仅含 `RedisConnectionError`/`ConnectionError`），
   但本次没有为此新增测试（超出 Task 7 允许范围），属未证实的推断，留作后续观察项。
5. **`test_celery_tasks.py` 未做微调**：第 1 步 RED 的失败点与简报预期不同，但仍是真实
   失败，按「优先不改测试」的约束保持原样。
6. **`tasks.md` 3.2 未勾**：硬约束禁止修改 `tasks.md`（当前仍为 `- [ ] 3.2`），请由
   Comet 流程/协调者在 verify-archive 阶段勾销。
7. 本地 Python 为 3.11.16 / pytest 9.1.1；全部测试命令均带 `--no-cov`；未触网、未起
   docker（集成 harness 走注入的假 `execute`，沙箱不实际启动）。
