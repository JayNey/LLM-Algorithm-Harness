# fix-benchmark-run-budget 验证报告

- 日期：2026-11-03
- 分支：`tweak/20261103/fix-benchmark-run-budget`
- 提交：`016d1fa`（`tweak: 让基准运行预算达到上限时暂停`）、`f892351`（`tweak: 预算恰好在末尾耗尽时完成运行`）
- 工作流：tweak；`verify_mode: full`（含 delta spec）
- 产物语言：zh-CN
- 规模评估：`comet state scale` → full（6 tasks、delta spec 1 个能力、18 个变更文件）

## 范围

验证“基准运行填写预算不再必失败，且达到运行级预算上限时按单元边界暂停”这一修复，覆盖：

- `src/harness.py`：非 task-service 路径接受 `budget_cap_usd + budget_action="auto_stop"`，用 `RunCostMonitor` 按单元结算已知成本，在下一个单元派发前暂停；重放检查点结果也计入预算。
- `api/services/benchmark_service.py`：为带 `budget_cap_usd` 的基准运行设置 `budget_action="auto_stop"`，沿用既有 `executor.paused → run/AsyncTask paused` 路径与检查点。
- 回归测试：`tests/test_benchmark_run_budget.py`（新增）、`tests/test_api_experiment_benchmark.py`、`tests/test_cost_strategy.py`。
- delta spec：`openspec/changes/fix-benchmark-run-budget/specs/api/experiment-management/spec.md`。

## 命令与结果

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest -m "not online" -q --no-cov` | 3749 passed，11 skipped，0 failed，退出码 0（489.85s） |
| `python3 -m pytest tests/test_benchmark_run_budget.py tests/test_cost_strategy.py tests/benchmark tests/test_api_experiment_benchmark.py tests/test_benchmark_task.py tests/test_budget_coverage.py -q --no-cov` | 177 passed，0 failed，退出码 0 |
| `comet classic openspec -- validate fix-benchmark-run-budget --type change --strict --no-interactive` | `Change 'fix-benchmark-run-budget' is valid`，退出码 0 |
| `python3 -m ruff check`（5 个改动文件） | All checks passed，退出码 0 |
| `python3 -m black --check`（5 个改动文件） | 5 files would be left unchanged，退出码 0 |
| `python3 -m mypy src/harness.py api/services/benchmark_service.py --ignore-missing-imports` | 本次改动文件无错误；仓库既有 3 个错误位于 `api/files/parsing.py:93`、`api/services/cost_alert_service.py:170-171`（非本次改动） |

## 完整验证检查项

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 1. tasks.md 全部完成 | PASS | 6/6 勾选；build 守卫 13/13 通过 |
| 2. 实现符合 `design.md` 高层设计决策 | PASS | 继续走非 task-service 路径、仅接受 auto_stop、已知成本结算、重放计入、复用既有 paused/检查点，均按 design 落地 |
| 3. 实现符合 Design Doc | N/A | tweak 不产出 `docs/superpowers/specs/` Design Doc（`design_doc: null`），以 `<classic-change-dir>/design.md` 承担设计说明 |
| 4. 能力规格场景全部通过 | PASS | 见下方场景覆盖表 |
| 5. proposal.md 目标已满足 | PASS | 带预算基准不再抛 `Run-level cost budgets require the task service run path`；达到上限暂停而非失败；未填预算行为不变；无 API/DB/前端契约变化 |
| 6. delta spec 与 design 无矛盾 | PASS | delta spec 的暂停、完成、恢复、无预算四个场景与 design 决策逐条一致，无漂移 |
| 7. 关联设计文档可定位 | N/A | tweak 无 Design Doc；`design.md` 为唯一设计说明 |

## Delta spec 场景覆盖

| 场景 | 覆盖方式 | 结果 |
| --- | --- | --- |
| 达到预算后暂停 | `test_non_task_harness_pauses_at_budget_cap_instead_of_failing`：第 2 个单元后超出 1.0，第 3 个单元不派发，`harness.paused=True`；`test_benchmark_executor_reports_budget_pause` 验证真实 `BenchmarkExecutor` 同样暂停；`tests/test_benchmark_task.py::test_execute_marks_benchmark_paused_from_other_connection` 覆盖既有 run/AsyncTask paused 映射 | PASS |
| 未达到预算正常完成 | `test_budget_not_reached_runs_every_unit`：cap 10.0、3 个单元全部执行且 `paused=False`；`test_budget_reached_on_last_unit_completes_instead_of_pausing`：cap 恰好在最后一个单元耗尽时按完成处理，不进入无法推进的 paused | PASS |
| 恢复后重新判断且不重复执行 | `test_resumed_replay_counts_toward_budget_without_rerunning`：重放已完成单元计入累计、模型调用次数不变；预算仍不足时再次暂停 | PASS |
| 无预算运行保持不变 | `tests/benchmark/test_executor.py::TestBenchmarkExecutor::test_execute_runs_harness_and_collects_results` 及 `tests/test_api_experiment_benchmark.py::TestBenchmarks::test_run_results_and_learning_curve`；全量套件通过 | PASS |

## 回归证据（RED → GREEN）

- RED：新增 `test_non_task_harness_pauses_at_budget_cap_instead_of_failing` 在修改前以 `ValueError: Run-level cost budgets require the task service run path`（`src/harness.py:137`）失败，复现复习报告 P0-4。
- RED：新增 `test_run_with_budget_uses_auto_stop_harness_config` 在服务改动前失败于 `config.budget_action is None`。
- RED：验证第二轮发现“cap 恰好在最后一个单元耗尽会错误进入 paused”，先以 `test_budget_reached_on_last_unit_completes_instead_of_pausing` 复现失败，再修复为“仍有未派发单元才暂停”。
- GREEN：上述测试及全量后端测试通过。

## 集成代码审查

`review_mode: off`（本 tweak 的持久化配置）。按 `/comet-verify` 规则跳过自动 code review，原因：改动为单一预算控制路径的后端行为修复，不涉及鉴权、外部输入解析、数据库 schema 或前端契约；已由 RED/GREEN 回归、177 项相关测试、3749 项全量测试、OpenSpec 严格校验、ruff/black 覆盖正确性与边界。

## 例外与限制

1. 真实供应商调用与 Celery worker 未在本机重跑：预算暂停逻辑通过替换策略运行时验证，未使用在线模型凭据；worker 状态映射复用既有测试。
2. 基准运行没有编辑预算的接口/UI。预算暂停后若上限不变，恢复会再次暂停；用户需要以更高预算新建运行。该行为符合“预算仍不足则再次暂停”，但当前产品未提供原地调高预算的入口。
3. 达到上限发生在单元边界，在途调用仍可能超过上限；未知定价/用量的成本不虚构金额，预算判断使用已知成本下限。
4. `mypy` 全仓仍有 `api/files/parsing.py` 与 `api/services/cost_alert_service.py` 的既有错误，与本次改动无关，未在本 change 内修复。

## 结论

PASS。无 CRITICAL/IMPORTANT 问题；delta spec 四个场景均有对应回归，未填预算路径与既有个体预算暂停/取消路径保持不变。
