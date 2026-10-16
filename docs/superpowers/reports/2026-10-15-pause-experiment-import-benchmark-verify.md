# pause-experiment-import-benchmark 验证报告

结论：PASS

## 范围

- change：`pause-experiment-import-benchmark`
- 分支：`tweak/20261015/pause-experiment-import-benchmark`
- 验证模式：full。本次有 delta spec；`comet state scale` 统计 3 个任务、1 个 delta spec、28 个变更文件，结果为 full。
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 升级判定

相对 `base_ref` 的路径数超过 tweak 文件数提示阈值（决策时 27，规模评估时 28）。实现分布在实验循环、导入循环和基准循环。用户在文件数提示后选择继续 tweak，不升级为完整 classic。跨模块协调已在构建前由用户选择继续 tweak。

## 完整性

- tasks.md 3/3 已勾选。
- delta spec `async-task-queue` 修改 3 条既有需求，各增加暂停场景。恢复接口仍只接受评估任务。

| 场景 | 证据 |
| --- | --- |
| 暂停正在执行的实验 | `src/experiment.py` 在每个组合开始前调用 `_pause_requested`；暂停后不写 `finished_at`。`api/services/experiment_service.py` 把仍为 `running` 的实验写成 `paused`。`tests/test_experiment_task.py::test_runner_skips_later_combinations_after_pause` 断言只执行了第一个组合。`tests/test_experiment_task.py::test_run_experiment_task_keeps_paused_status` 断言任务和实验保持 `paused` |
| 暂停正在执行的导入 | `api/files/service.py` 在每道题前和 `merge_dataset` 前检查；`api/files/store.py` `pause_job` 只把 `running` 作业写成 `paused`。`tests/test_api_files.py::test_paused_import_does_not_write_remaining_problems` 断言数据集没有 `skip-me`。`tests/test_import_task.py::test_run_import_task_keeps_paused_status` 断言任务保持 `paused` |
| 暂停正在执行的基准 | `src/harness.py` `_run_strategy` 在每道题前停止；`src/benchmark/executor.py` 把暂停传给 harness。`api/services/benchmark_service.py` 把仍为 `running` 的运行写成 `paused`。`tests/test_harness.py::test_harness_skips_later_problems_after_pause` 断言只执行了 `first`。`tests/test_benchmark_task.py::test_run_benchmark_task_keeps_paused_status` 断言任务和运行保持 `paused` |

## 正确性

- 三类 worker 用 `populate_existing()` 从另一条连接读取 `AsyncTask.status == paused`。
- 已经开始的组合、导入项或基准题可以做完。并行实验在提交下一个组合前检查，已提交的 future 仍会完成。
- 暂停后的结束路径返回 `paused`，不再把任务写成 `completed` 或 `failed`。实验和基准的失败写入会跳过已经是 `paused` 的记录。
- `src/task_manager.py` `resume_task` 仍在 `task_type != evaluation` 时拒绝。评估暂停与恢复未改。
- 与 `design.md` 的四项决定一致：协作式暂停、按现有循环设安全边界、读取时绕过 identity map、结束写入不覆盖暂停。
- proposal 的目标已满足：暂停接口地址和请求体不变；不新增表或列；业务状态可以停在 `paused`。

## 一致性

- tweak 预设没有 Superpowers Design Doc（`design_doc` 为空）。设计依据是 `openspec/changes/pause-experiment-import-benchmark/design.md`。
- delta spec 与 `design.md` 无矛盾。`docs/superpowers/specs/` 没有本次 tweak 的设计文档需要对照。

## 安全

- 暂停读取按任务类型、实体标识和用户标识过滤。
- 导入暂停后不调用 `merge_dataset`，未完成的题目不会进入数据集。
- 未新增密钥、凭据或日志中的敏感信息。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/test_experiment_task.py tests/test_import_task.py tests/test_benchmark_task.py tests/test_harness.py tests/test_api_files.py tests/test_api_experiment_benchmark.py -q --no-cov` | 136 passed，退出码 0 |
| `python3 -m ruff check` 上述 15 个实现和测试文件 | All checks passed，退出码 0 |
| `python3 -m black --check` 上述 15 个文件 | 15 files would be left unchanged，退出码 0 |
| `comet classic openspec -- validate pause-experiment-import-benchmark --strict --type change` | Change is valid，退出码 0 |
