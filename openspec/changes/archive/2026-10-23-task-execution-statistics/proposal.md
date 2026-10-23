## Why
性能接口仍返回评估耗时与成功率占位值，无法判断真实业务任务执行表现。

## What Changes
- 完善任务状态与进度更新的开始、结束时间记录。
- 从实际 AsyncTask 持久化记录聚合全部业务任务与评估任务的平均执行秒数和成功率。
- 明确空样本、无效时间、暂停重试和数据库不可用的行为。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `async-task-queue`: 增加实际执行时间与性能统计验收要求。

## Impact
任务管理器、现有管理员性能接口及其测试。复用已有时间字段，无数据库迁移。
