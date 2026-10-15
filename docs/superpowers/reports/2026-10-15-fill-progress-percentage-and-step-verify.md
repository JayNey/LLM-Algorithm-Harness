# fill-progress-percentage-and-step 验证报告

结论：PASS

## 范围

- change：`fill-progress-percentage-and-step`
- 分支：`tweak/20261015/fill-progress-percentage-and-step`
- 验证模式：full。本次有 delta spec；`comet state scale` 统计 3 个任务、1 个 delta spec、24 个变更文件，结果为 full。
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 升级判定

相对 `base_ref` 的路径数为 24，超过 tweak 文件数提示阈值。实现分布在实验循环、导入循环和基准循环。用户在跨模块信号和文件数提示后都选择继续 tweak，不升级为完整 classic。

## 完整性

- tasks.md 3/3 已勾选。
- delta spec `async-task-queue` 修改实验、导入、基准三条既有需求，要求任务进度包含 0 到 100 的百分比和当前步骤，且当前步骤不含题目正文。

| 场景 | 证据 |
| --- | --- |
| 查询实验进度 | `src/experiment.py` 在每个组合开始前调用 `_report_combination`，只传入模型名、策略名和重复序号。`api/services/experiment_service.py` 在任务仍为 `running` 时写入进度。`tests/test_experiment_task.py::test_execute_records_percentage_and_current_step` 断言两步为 `demo-model/vanilla/1`、`demo-model/vanilla/2`，百分比为 0 和 50，且步骤不含题目正文 |
| 查询导入进度 | `src/tasks/imports.py` 用已处理数和总数计算百分比，当前步骤为条目序号。`tests/test_import_task.py::test_run_import_task_reports_progress_and_completes` 断言百分比为 50、当前步骤为 `2`，进度文本不含题目正文 |
| 查询基准进度 | `src/harness.py` `_emit_problem_progress` 在每道题执行前上报策略名和题目标识。`src/benchmark/executor.py` 把回调传给 harness，`api/services/benchmark_service.py` 写入任务进度。`tests/test_harness.py::test_run_reports_current_step_before_each_problem` 断言顺序为 `vanilla/first`、`vanilla/second`。`tests/test_benchmark_task.py::test_execute_records_percentage_and_current_step` 断言百分比为 0 和 50 |

## 正确性

- 百分比与 `current` / `total` 使用同一分母。`src/tasks/support.py` `progress_percentage` 在总数为 0 时返回 0，其余限制在 0 到 100。
- 进度只在任务状态仍为 `running` 时覆盖，暂停、完成和失败不会把已写入的进度清掉。
- 当前步骤只含定位信息：实验是 `模型/策略/重复序号`，导入是条目序号，基准是 `策略/题目标识`。
- 与 `design.md` 的决定一致：不新增表或列，不改导入作业进度接口，不改评估进度口径，导入仍按原有节奏上报。
- proposal 的目标已满足：任务查询能看到百分比和当前步骤。暂停和恢复行为未改。

## 一致性

- tweak 预设没有 Superpowers Design Doc（`design_doc` 为空）。设计依据是 `openspec/changes/fill-progress-percentage-and-step/design.md`。
- delta spec 与 `design.md` 无矛盾。`docs/superpowers/specs/` 没有本次 tweak 的设计文档需要对照。

## 安全

- 进度写入按任务类型、实体标识和用户标识过滤。
- 当前步骤不包含题目正文、上传内容或密钥。
- 未新增硬编码密钥或凭据。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/test_experiment_task.py tests/test_import_task.py tests/test_benchmark_task.py tests/test_harness.py -q --no-cov` | 54 passed，退出码 0 |
| `python3 -m ruff check` 上述 11 个实现和测试文件 | All checks passed，退出码 0 |
| `python3 -m black --check` 上述 11 个文件 | 11 files would be left unchanged，退出码 0 |
| `comet classic openspec -- validate fill-progress-percentage-and-step --strict --type change` | Change is valid，退出码 0 |
