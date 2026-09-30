# Proposal: 断点续传的可视化与运行管理（issue #88）

## Why

断点续传的核心能力（任务持久化、`--run-id`/`--resume`、指纹校验、不重复执行已完成单元）已由 TaskService 交付，但 issue #88 指出的运维面缺口真实存在：用户无法列出可恢复的运行、启动时不知道存在未完成的同类运行、无法清理已完成运行的状态文件、运行的成本累计不可见。

## What Changes

- 新增 `harness runs list [--all]`：列出输出目录下的任务运行——run_id、状态、完成进度（completed/total）、累计已知定价成本（由已完成单元的 llm_traces 结算，与 #56b 同口径）、更新时间；默认只显示可恢复（未完成）的运行，`--all` 显示全部。
- 启动检测提示：`harness run` 未带 `--resume` 时，若输出目录存在 config+dataset 指纹匹配的未完成运行，打印提示（run_id 与进度）并建议 `--resume --run-id`；不做交互式询问（自动化友好，作为对 issue 文案的偏差记录）。
- 新增 `harness runs clean [--force]`：删除已完成运行的任务状态文件，默认逐个确认，`--force` 跳过确认；未完成运行不在清理范围。
- 成本累计口径：仅统计定价与 usage 已知的调用，未知计数呈现（复用 cost_strategy.result_cost）。

## Capabilities

### New Capabilities

- `run-state-visibility`: 运行列表、可恢复性提示与状态清理的验收要求。

### Modified Capabilities

（无——TaskService 持久化与 resume 语义不变）

## Impact

- 代码：新增 `src/runs.py`（聚合与提示辅助）；`src/main.py` 新增 `runs` 子命令与 run 启动提示；新增 `tests/test_runs_visibility.py`；README 更新。
- 兼容性：只读消费任务记录 + 显式清理命令；执行路径不变。
