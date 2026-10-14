## 1. 数据模型与迁移（新增 model 字段）

- [ ] 1.1 在 `api/db/models.py` 的 `Evaluation` 增加 `model` 列，并新增一条 Alembic 迁移（`upgrade` 增加对既有行可空的 `model` 列、`downgrade` 对称删除）。验证：空库上 `alembic upgrade head` → `downgrade base` → 再 `upgrade head` 往返无报错，`evaluations.model` 存在。
- [ ] 1.2 `api/models.py` 的 `EvaluationCreateRequest` 增加必填 `model` 字段；`create_evaluation` 与 `create_evaluation_async` 持久化 `model` 到 `Evaluation`。验证：单测断言创建后 `evaluations.model` 等于请求值；缺少 `model` 的请求返回 422 校验失败。

## 2. 真实执行编排（service 层）

- [ ] 2.1 在 `EvaluationService` 增加真实执行编排 `_execute(evaluation_id, owner_id)`：先解析凭证 `auth.llm_config(api_key_id, owner_id, model)` 与题目 `ProblemStore.get_by_problem_id`，凭证不可解析或缺少 `model` 时在执行任何单元前把评估置 `failed` 并写 `error_message`。验证：单测覆盖「凭证不可解析→failed 且无 `EvaluationResult` 行」「缺 model→failed 不发起 LLM 调用」。
- [ ] 2.2 逐 (策略 × 题目) 单元经 `AlgorithmHarness` 执行路径产出 `ExecutionResult`，映射为 `EvaluationResult` 并以 `(evaluation_id, problem_id, strategy_name)` 为幂等键 upsert；聚合更新 `completed_count`/`failed_count`。题目缺失的单元记为失败并写原因、其余题目继续。验证：单测（mock LLM/沙箱）断言每单元一条结果行、计数口径 `completed+failed==单元总数`、部分题目缺失时其余单元正常执行。
- [ ] 2.3 把每单元真实花费累计到 `spent_usd`，达到 `budget_cap_usd` 时经 `TaskService` 的 `pause_when` 停止调度后续单元并置 `paused`、保留已完成结果。验证：单测覆盖「达上限→paused 且未开始单元不执行、已完成结果与 spent_usd 保留」「无上限→跑完全部单元」。

## 3. worker 接入与恢复

- [ ] 3.1 替换 `src/tasks/evaluation.py` 中 `run_evaluation_task` 的 mock `worker()`，改为驱动 2.1–2.3 的真实执行编排；保持既有状态机、入队时序与 `start/pause/resume/cancel` 语义不变，执行终态（completed/paused/failed）回写评估与关联 `AsyncTask` 一致。验证：`run_evaluation_task` 单测（mock harness/LLM/沙箱）断言三种终态回写正确、不再产生 `mock` 结果。
- [ ] 3.2 对 `paused`/`failed` 评估重新发起执行时从未完成单元继续，已完成单元不重复执行、不产生重复 `EvaluationResult`，计数与 `spent_usd` 在既有基础上续增。验证：单测——预算暂停后提高预算再 resume，仅剩余单元执行、无重复结果行、`completed_count` 续增。

## 4. 测试与质量门禁

- [ ] 4.1 补齐/更新受影响测试（`tests/test_evaluation*`、`test_api_database.py`、`test_api_auth.py` 等），全程 mock LLM 与沙箱、不发起在线调用。验证：`pytest -m "not online" --no-cov -q` 全绿。
- [ ] 4.2 通过全部 CI 等价门禁。验证：`ruff check .`、`ruff format --check`、`black --check .`、`mypy src/ --ignore-missing-imports`、`python scripts/find_missing_encoding.py`、`pytest tests/test_utf8_io.py -q --no-cov` 全部通过。
