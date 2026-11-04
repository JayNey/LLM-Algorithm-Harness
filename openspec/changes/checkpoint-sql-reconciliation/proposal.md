## Why
Issue #337：文件检查点先于 SQL 提交，worker 丢失后已完成单元被跳过，结果与费用永久缺失。

## What Changes
- 恢复时先对账检查点终态单元，再执行未完成单元。
- 结果与费用按稳定题目×策略键在同一事务幂等更新。
- 完成后发布覆盖全部结果的终态快照。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `async-task-queue`：明确评估检查点与业务结果的恢复一致性。

## Impact
仅修改评估 worker 编排及对应测试，无 public API、schema 或依赖变更。
