# evaluation-progress-percentage-and-step 验证报告

结论：PASS

## 范围

- change：`evaluation-progress-percentage-and-step`
- 分支：`tweak/20261015/evaluation-progress-percentage-and-step`
- 验证模式：full。本次有 delta spec；`comet state scale` 统计 1 个任务、1 个 delta spec、16 个变更文件，结果为 full。
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 升级判定

相对 `base_ref` 的路径数为 16，超过 tweak 文件数提示阈值。代码改动是 `src/task_service.py`、`src/tasks/evaluation.py` 和 `tests/test_celery_tasks.py`，其余是 change 元数据。用户选择继续 tweak，不升级为完整 classic。

## 完整性

- tasks.md 1/1 已勾选。
- delta spec `async-task-queue` 修改「评估可以作为异步任务执行」，要求任务进度包含 0 到 100 的百分比和当前步骤，当前步骤是即将执行单元的策略和题目标识，且不含题目正文。暂停后保留最后一次进度。

| 场景 | 证据 |
| --- | --- |
| 查询评估进度 | `src/task_service.py` 在提交单元前调用 `on_unit_started`。`src/tasks/evaluation.py` 的 `report_progress` 在任务仍为 `running` 时写入 `percentage` 和 `current_step`。`tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_records_percentage_and_current_step` 断言两步为 `vanilla/p1`、`vanilla/p2`，百分比为 0 和 50，且步骤不含题目正文 |
| 暂停后保留评估进度 | 同一 `report_progress` 在任务不再是 `running` 时不覆盖进度。`tests/test_celery_tasks.py::TestRunEvaluationTaskIntegration::test_run_evaluation_task_pause_keeps_progress` 断言任务为 `paused`，进度仍是百分比 0、当前步骤 `vanilla/p1`，且只执行了第一个单元 |

既有提交、入队、取消和重启场景没有被这次 delta 改写行为。`tests/test_celery_tasks.py` 与 `tests/test_task_service.py` 全量 41 项通过。

## 正确性

- 百分比与已结束单元数、单元总数使用同一分母。`src/tasks/support.py` 的 `progress_percentage` 在总数为 0 时返回 0，其余限制在 0 到 100。
- 单元开始前的 `current_step` 是 `策略/题目标识`。同一份进度写入任务记录和 Celery `PROGRESS`。
- 与 `design.md` 的决定一致：不新增表、列或接口，不改评估详情进度模型，不改暂停、恢复和取消。
- proposal 的目标已满足：评估任务查询能看到百分比和当前步骤。

## 一致性

- tweak 预设没有 Superpowers Design Doc（`design_doc` 为空）。设计依据是 `openspec/changes/evaluation-progress-percentage-and-step/design.md`。
- delta spec 与 `design.md` 无矛盾。`docs/superpowers/specs/` 没有本次 tweak 的设计文档需要对照。

## 安全

- 进度只写调用方这次评估关联的任务记录，并在状态不再是 `running` 时停止覆盖。
- 当前步骤不包含题目正文、模型输出或密钥。
- 未新增硬编码密钥或凭据。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/test_celery_tasks.py tests/test_task_service.py -q --no-cov` | 41 passed，退出码 0 |
| `python3 -m ruff check src/task_service.py src/tasks/evaluation.py tests/test_celery_tasks.py` | All checks passed，退出码 0 |
| `python3 -m black --check src/task_service.py src/tasks/evaluation.py tests/test_celery_tasks.py` | 3 files would be left unchanged，退出码 0 |
| `comet classic openspec -- validate evaluation-progress-percentage-and-step --strict --type change` | Change is valid，退出码 0 |
