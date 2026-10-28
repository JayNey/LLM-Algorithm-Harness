## Why

Issue #295：通过任务接口取消实验时只修改 AsyncTask，Experiment 仍可能显示 running 并无法删除。Worker 的启动、进度、收尾与 Celery 状态回填还可能覆盖取消状态。

## What Changes

- 在同一事务内同步实验关联任务和实验的状态、时间与错误，保留所有者隔离和终态约束。
- 串行化取消与 Worker 状态迁移，防止过期 ORM 对象、晚到成功/异常与 Celery 回填恢复已取消任务。
- 取消后停止后续实验组合，刷新详情显示 cancelled，允许按既有规则删除。
- 添加任务、Worker、服务与 API 回归测试，覆盖双连接竞争的两种先后顺序。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `async-task-queue`：补充实验取消状态同步、协作停止、晚到结果保护与所有权约束。

## Impact

主要修改 src/task_manager.py、src/tasks/experiment.py、api/services/experiment_service.py 以及对应回归测试；不增加数据库 schema、依赖或 API。

用户已选择 A2：接受此范围的跨模块修复继续 tweak，使用新分支。Comet workspace prepare 创建 comet/experiment-cancellation-sync，目标 main。实现采用单一 change，保留现有删除规则。
