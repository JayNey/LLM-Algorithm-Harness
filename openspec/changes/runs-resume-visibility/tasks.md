# Tasks: runs-resume-visibility

## Task 1: 聚合辅助模块

**文件**: 新增 `src/runs.py`、`tests/test_runs_visibility.py`

- [x] `summarize_run`：进度/状态/成本/unknown 结算（result_cost 口径）、resumable 判定
- [x] `find_matching_unfinished`：双指纹匹配且未完成
- [x] 单元测试：成本手算对账、unknown 计数、resumable 判定、指纹匹配

## Task 2: CLI 与启动提示

**文件**: `src/main.py`、`tests/test_runs_visibility.py`

- [x] `harness runs list [--all]`（updated_at 倒序）
- [x] `harness runs clean [--force]`（仅已完成；无 --force 逐个确认）
- [x] run 启动提示：指纹匹配的未完成运行打印建议命令；不阻塞
- [x] 端到端测试：list 输出、clean 行为（确认/force/跳过未完成）、启动提示触发与不触发

## Task 3: 文档与回归

**文件**: `README.md`

- [x] 运行管理说明（runs list/clean、启动提示、成本口径、与 --resume 的关系）
- [x] 全量测试 + `openspec validate` 通过
