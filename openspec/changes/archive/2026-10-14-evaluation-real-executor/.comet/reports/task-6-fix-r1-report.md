# Task 6 review-fix R1 报告

- **状态**：DONE
- **分支**：`comet/evaluation-real-executor`
- **BASE**：`4bfd795`
- **commit**：`7bef2d8`（parent = `4bfd795`，本次只追加一个 commit）
- **改动文件**（严格限定两个）：`src/tasks/evaluation.py`、`tests/test_celery_tasks.py`
- **未触碰**：`src/models.py`、plan / design / tasks.md / ledger 及任何其他文件

---

## 1. C1 CRITICAL — `_to_domain_problem` 对真实数据 100% 转换失败

### 根因复核（已实测确认）

```
$ python3 -c "import json; rows=json.load(open('data/problems.json')); \
  print('count', len(rows)); print('keys of first:', sorted(rows[0].keys())); \
  print('has source_platform:', sum(1 for r in rows if 'source_platform' in r))"
count 12
keys of first: ['constraints', 'description', 'difficulty', 'problem_id', 'tags', 'test_cases', 'title']
has source_platform: 0
```

- 真实题库 12 条记录 **0 条**含 `source_platform` / `source_url` 键 → 导入后 ORM 列为 NULL（`api/db/models.py:39-40` 为 `Mapped[str | None]`）。
- domain `src/models.py:77` 为 `source_platform: str = Field("legacy")`，**非 Optional**，显式传 `None` → pydantic `ValidationError`。
- `_resolve_execution_context` 捕获后并入 `missing_problems` → `problem_map` 恒空 → 每个单元抛 "Problem X not found in problem store"，评估全单元 failed。

### 修复 diff 摘要（`src/tasks/evaluation.py`，`_to_domain_problem`）

```diff
-    return DomainProblem(**data)
+    # NULL 列省略而非显式传 None，使 domain 默认值生效（``tags`` 经 ``or []`` 兜底为
+    # ``[]``，不会被过滤）。
+    return DomainProblem(**{k: v for k, v in data.items() if v is not None})
```

组装 dict 的内容未变（`tags` 仍是 `row.tags or []`），只在**展开时过滤掉值为 `None` 的键**，语义与简报参考实现一致：

- 真实数据（`source_platform` / `source_url` / `constraints` 为 NULL）→ 省略这些键 → domain 默认值生效（`"legacy"` / `None` / `None`）→ **转换成功**。
- `tags` 经 `or []` 兜底为 `[]`（非 `None`）→ **不会被过滤**，行为不变。
- 必需且无默认值的字段（`problem_id` / `title` / `description` / `difficulty` / `test_cases`）若为 `None` → 被省略 → pydantic 报 `field required` → 仍是 `ValidationError` → 照旧并入 `missing_problems`，**失败语义原样保留，未被吞掉**。
- `test_cases` 为 `None` 时同理：`assign_test_case_sources` validator 抛 ValueError（pydantic 包成 `ValidationError`）→ 并入 missing。

同时在该函数 docstring 增补一段说明（NULL 列省略的原因、默认值、以及保留失败语义的边界），无行为影响。

---

## 2. I1 IMPORTANT — 测试 fixture 硬编 `source_platform`，掩盖了 C1

### 测试改动摘要（`tests/test_celery_tasks.py`）

| 位置 | 改动 |
| --- | --- |
| `_seed_problem`（集成测试真实 ORM seed） | `source_platform="leetcode"` → `source_platform=None`，并加注释说明「真实导入形状：`data/problems.json` 不含该键 → 列为 NULL」 |
| `test_missing_problem_recorded_not_fatal` 的 `orm_row` | `source_platform="leetcode"` → `None`；**新增断言** `converted.source_platform == "legacy"`、`converted.source_url is None`，显式钉住 C1 的修复语义（domain 默认值生效） |
| `test_invalid_problem_row_recorded_as_missing` 的 `bad_row` | `source_platform="legacy"` → `None`（与真实形状一致）；该用例的失败原因仍是 `description=""` 短于 `min_length=10`，断言「`bad` 落入 `missing_problems` 且不在 `problem_map`」**保持不变** |

未新增/删除任何测试用例，未修改任何其他 fixture 或断言。

---

## 3. RED 证据（**先改测试、未改 `_to_domain_problem`**）

### 3.0 改动前基线（证明 C1 被硬编 fixture 完全掩盖）

```
$ python3 -m pytest tests/test_celery_tasks.py -q --no-cov
======================== 22 passed, 1 warning in 1.63s =========================
```

### 3.1 定向（简报指定命令）

```
$ python3 -m pytest tests/test_celery_tasks.py -k "resolve_execution_context or run_evaluation_task or problem" -v --no-cov
...
FAILED tests/test_celery_tasks.py::TestResolveExecutionContext::test_missing_problem_recorded_not_fatal - AssertionError: assert 'p1' in {}
 +  where {} = _EvalContext(llm_config=<object object at 0x10d31cee0>, problem_map={}, missing_problems={'p1', 'missing'}).problem_map
FAILED tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_completes_all_units - AssertionError: assert 'failed' == 'completed'
FAILED tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_budget_pause - AssertionError: assert 'failed' == 'paused'
FAILED tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_unknown_pricing_honest - AssertionError: assert 'failed' == 'completed'
============ 4 failed, 11 passed, 7 deselected, 1 warning in 1.65s =============
```

失败原因与 C1 预期完全一致：`problem_map={}`、`missing_problems={'p1','missing'}` → 单元失败 → `evaluation.status='failed'`（而非 `completed` / `paused`）。

### 3.2 全文件

```
$ python3 -m pytest tests/test_celery_tasks.py -q --no-cov
=================== 4 failed, 18 passed, 1 warning in 2.06s ====================
```

`test_invalid_problem_row_recorded_as_missing` 在 RED 阶段仍 passed —— 符合预期（其失败原因是 `description=""`，与 `source_platform` 无关），说明该用例没有变成假信号。

---

## 4. GREEN 证据（修完 `_to_domain_problem` 后）

### 4.1 定向（简报指定命令）

```
$ python3 -m pytest tests/test_celery_tasks.py -k "resolve_execution_context or run_evaluation_task or problem" -v --no-cov
...
tests/test_celery_tasks.py::TestResolveExecutionContext::test_missing_problem_recorded_not_fatal PASSED
tests/test_celery_tasks.py::TestResolveExecutionContext::test_invalid_problem_row_recorded_as_missing PASSED
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_completes_all_units PASSED
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_credential_failure_no_results PASSED
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_budget_pause PASSED
tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_unknown_pricing_honest PASSED
================= 15 passed, 7 deselected, 1 warning in 1.64s ==================
```

### 4.2 全文件回归

```
$ python3 -m pytest tests/test_celery_tasks.py -q --no-cov
======================== 22 passed, 1 warning in 1.47s =========================
```

### 4.3 项目全量套件（TDD 技能要求：不止跑本文件）

```
$ python3 -m pytest -q --no-cov -p no:randomly
========== 1650 passed, 6 skipped, 113 warnings in 154.45s (0:02:34) ===========
```

无 failure、无 error；warnings 均为既有（pydantic V2 deprecation、SADeprecationWarning、matplotlib legend、scipy precision loss），与本次改动无关。

### 4.4 Lint / format

```
$ python3 -m ruff check src/tasks/evaluation.py tests/test_celery_tasks.py
All checks passed!
$ python3 -m ruff format --check src/tasks/evaluation.py tests/test_celery_tasks.py
2 files already formatted
```

---

## 5. 顾虑

1. **无阻塞性顾虑**。C1/I1 均已按简报语义修复，失败语义未被放宽，`src/models.py` 未触碰。
2. 供主会话知晓的**范围外观察**（本轮未动，因硬约束只允许改两个文件）：
   - 导入链路（`api/datasets.py` / `docs/importing.md` 一侧）对 `data/problems.json` 中缺失的 `source_platform` / `source_url` 仍是落 NULL。本修复让消费侧对 NULL 健壮，但若希望 domain 的 `source_platform` 反映真实来源（而非一律 `"legacy"`），需在导入侧补默认值 —— 属独立议题，不在本轮范围。
   - `_to_domain_problem` 的 `None` 过滤是「宽进」策略：若将来 domain 增加**允许显式 `None` 且默认值非 `None`** 的字段，过滤会静默改用默认值。目前 domain `Problem` 无此类字段（`constraints` / `source_url` 默认值本就是 `None`），故无实际风险；已在 docstring 中记录该取舍。

---

## 6. 提交

```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "fix(eval): omit None columns in ORM->domain problem conversion so real dataset converts (evaluation-real-executor 3.1 review-fix)"
```

- commit hash：`7bef2d8`（parent `4bfd795`）
- 实际入库统计：

```
$ git show --stat --oneline 7bef2d8
7bef2d8 fix(eval): omit None columns in ORM->domain problem conversion so real dataset converts (evaluation-real-executor 3.1 review-fix)
 src/tasks/evaluation.py    | 12 +++++++++++-
 tests/test_celery_tasks.py | 12 +++++++++---
 2 files changed, 20 insertions(+), 4 deletions(-)
```

- `git status` 确认：仅上述两个文件入库；本报告文件（`.comet/reports/task-6-fix-r1-report.md`）与主会话维护的 `subagent-progress.md` / `task-6-report.md` 仍是未跟踪/未暂存状态，未被 `git add`。
