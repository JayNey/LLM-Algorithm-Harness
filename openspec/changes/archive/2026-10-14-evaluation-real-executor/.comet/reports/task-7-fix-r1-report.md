# Task 7 Review-Fix Round 1 Report

- **状态**: DONE（I1 已修复，RED/GREEN 证据齐全，mutation 已还原）
- **分支 / commit**: `comet/evaluation-real-executor`，基线 `c72741b` → 修复提交 `273c180`
- **提交内容**: `tests/test_celery_tasks.py` 单行改动（1 file changed, 1 insertion(+), 1 deletion(-)）；`src/tasks/evaluation.py` 与 HEAD 无 diff（注入改动已撤销，未入库）

## I1 修复摘要

Reviewer 判定：`test_resume_after_pause_runs_only_remaining` 中 `assert ev.spent_usd >= first_spent`
在 fixture 每单元恒定 `cost=0.05` 场景下可被"累加改覆盖"回归绕过——覆盖后终局
`spent_usd == first_spent == 0.05`，`>=` 仍 PASS，而 tasks.md 3.2 点名要防的正是
"resume 后 spent_usd 重置"。

修复（L940）：

```diff
-        assert ev.spent_usd >= first_spent
+        assert ev.spent_usd > first_spent
```

理由：p2 在 resume 后必执行且 cost > 0，正确实现下累加结果严格大于 `first_spent`；
覆盖回归使 `spent_usd == first_spent`，严格大于变 False，被正确捕获。

## TDD 证据（mutation-style RED）

### 基线（新断言 + 正确实现）→ PASS

`python3 -m pytest tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining -v --no-cov`

```
========================= 1 passed, 1 warning in 1.75s =========================
```

### RED —— 临时注入覆盖回归

注入：`src/tasks/evaluation.py` `on_unit_finished` 中
`evaluation.spent_usd = (evaluation.spent_usd or 0.0) + cost` → `evaluation.spent_usd = cost`

目标测试失败输出摘录：

```
test_resume_after_pause_runs_only_remaining FAILED [100%]
    assert ev.spent_usd > first_spent
E   assert 0.05 > 0.05
========================= 1 failed, 1 warning in 2.05s =========================
```

失败形态与预期完全一致：覆盖回归把终局 `spent_usd` 重置回 0.05，`>` 断言捕获（旧
`>=` 在此场景会误 PASS，即 I1 指出的绕过）。

### GREEN —— 恢复 evaluation.py（`git checkout -- src/tasks/evaluation.py`）

```
python3 -m pytest tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_resume_after_pause_runs_only_remaining -v --no-cov
========================= 1 passed, 1 warning in 1.48s =========================

python3 -m pytest tests/test_celery_tasks.py -q --no-cov
======================== 23 passed, 1 warning in 1.29s =========================
```

全文件 23 项测试通过，无失败、无错误（仅项目既有 Pydantic V2 deprecation warning）。

## 约束核对

- [x] 只改测试文件这一行；src/、plan/design/tasks.md/ledger 均未触碰
- [x] `git diff --stat`（提交前）仅 `tests/test_celery_tasks.py | 2 +-`
- [x] commit `273c180` 只含该一行改动
- [x] evaluation.py 注入已撤销，与 HEAD 无 diff

## 顾虑

无阻塞项。备注：pytest 输出中 `api/config.py:8` 的 Pydantic deprecation warning 为
既存问题，与本修复无关。
