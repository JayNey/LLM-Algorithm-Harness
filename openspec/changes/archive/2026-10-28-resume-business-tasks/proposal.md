## Why

Issue #306：通用暂停覆盖五种任务，但恢复仅支持 evaluation，导致实验、基准、导入和 A/B 无法继续。需补齐停止确认、持久化续跑以及并发恢复保护。

## What Changes

- 四类任务恢复沿用原 AsyncTask 和业务记录；保留检查点、进度、结果及费用。
- 暂停采用协作式停止，当前单元完成落盘后确认；确认前拒绝恢复。
- 恢复原子占用新执行标识；旧投递、重复投递和旧回调不改变新执行。
- 发布失败条件更新任务和业务状态，保留 evaluation 所有权、关联和容量限制。
- 补充接口文档和契约测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `async-task-queue`：扩展暂停恢复契约及执行代际保护。

## Impact

TaskManager、四类 Worker、服务及 runner 检查点、导入 job 存储、任务 API 文档与测试。无需新增数据库表或接口。
用户在识别跨模块协调信号后明确选择继续 tweak（1B），使用新分支（2B）；范围仍收敛为此单一 change，允许相应文件数量。
