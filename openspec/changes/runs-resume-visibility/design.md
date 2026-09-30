# Design: 断点续传可视化与运行管理

## 实现说明

### 聚合辅助（src/runs.py）

- `summarize_run(record) -> dict`：从 TaskRecord 派生 `{run_id, state, completed, total, updated_at, resumable, cost_usd, unknown_usage_results}`；成本由 `unit.result` 反序列化后经 `cost_strategy.result_cost` 结算（仅已知定价；unknown 单独计数），resumable = state 未完成（queued/running/paused/cancelled 等，completed 除外）。
- `find_matching_unfinished(service, config_fingerprint, dataset_fingerprint) -> list[record]`：指纹均匹配且未完成的运行，用于启动提示。

### CLI（src/main.py）

- `harness runs list [--all]`：按 updated_at 倒序输出表格行（stdout）；空列表提示。
- `harness runs clean [--force]`：仅针对已完成运行删除任务文件；无 `--force` 时逐个 `y/N` 确认，非交互 stdin 下默认不删除。
- `run` 启动提示：未带 `--resume` 且未指定 `--run-id` 时，创建任务前检测指纹匹配的未完成运行并打印提示（含建议命令）；不阻塞、不交互。
- 成本口径：result_cost（已知定价累计 + unknown 计数），与预算降级一致。

## 边界

- 运行状态文件仍由 TaskService 持有（`output_dir/tasks/<run_id>.json`），不新增 `.state/` 目录（issue 文案为建议布局，沿用既有持久化位置并在 README 说明）。
- `runs clean` 只删任务状态文件，不删除评估结果产物目录。
