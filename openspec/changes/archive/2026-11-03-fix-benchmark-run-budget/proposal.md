## Why

基准运行详情页提供“预算上限 USD（可选）”输入，但后端执行时走非 task-service 的 harness 路径，`AlgorithmHarness.run()` 只要看到 `budget_cap_usd` 就直接抛出 `Run-level cost budgets require the task service run path`，导致带预算的基准运行 100% failed；不填预算才正常。用户看到的“可填但必失败”输入与复习报告 P0-4 一致，必须修掉。

## What Changes

- 非 task-service 的 harness 运行路径支持 `budget_cap_usd` + `budget_action="auto_stop"`：按题目单元累计已知成本，达到上限后在下一个单元派发前暂停。
- 基准执行器继续走现有非 task-service 路径，保留 API 侧的用户暂停/取消检查与个人预算守卫，不引入第二套任务记录。
- `BenchmarkService` 为带预算的基准运行设置 `budget_action="auto_stop"`；未填预算时行为不变。
- 暂停沿用基准现有 paused 状态与单元检查点；恢复时重放已完成单元、重新判断预算，预算仍不足则继续暂停，不重复执行已完成题目。
- 增加回归测试：达到预算暂停、未达预算完成、无预算不变、恢复不重复已完成单元。
- 前端继续使用现有预算输入，无新增字段或接口变更。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `api/experiment-management`: 基准运行在携带 `budget_cap_usd` 时按已记录成本暂停并保留可恢复状态，而不是直接失败。

## Impact

- `src/harness.py`：非 task-service 运行级预算监测与暂停。
- `src/benchmark/executor.py`：预算运行继续使用现有执行入口。
- `api/services/benchmark_service.py`：为带预算的运行设置 `auto_stop` 预算动作。
- `tests/`：新增/扩展 harness 与基准预算回归测试。
- 无 API 契约、数据库 schema 或前端字段变更；CLI 既有 task-service 预算路径保持原行为。
