## Why
Issue #352：服务启动恢复将尚未启动的评估和实验 pending 草稿标为 failed，导致保存的配置不可启动。

## What Changes
- 保留无开始时间、无任务关联或提交历史的 pending 草稿。
- 用数据库原子条件恢复真正孤立的执行，保留活跃任务和终态。
- 回归重建服务、共享库第二实例、重复恢复及启动竞争。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `async-task-queue`: 明确评估和实验草稿与孤立执行的启动恢复边界。

## Impact
仅修改两个服务的恢复查询及相关测试，不增加 API、数据库字段或依赖。
