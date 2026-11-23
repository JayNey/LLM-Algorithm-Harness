# 修复已入队评估删除保护

## Why

Issue #511：评估入队后业务状态仍为 pending，当前删除入口仅检查业务状态，导致 Evaluation 被移除而 AsyncTask 继续 pending、占用用户并发额度。现有两阶段删除还允许提交在状态检查和文件清理之间进入。

## What Changes

- 有 pending/running/paused 关联评估任务时拒绝删除，提示先取消并等待执行停止。
- 列表、详情及异步响应的 `can_delete` 与实际删除保护保持一致。
- 删除与评估提交复用同一数据库事务锁；活动任务校验、文件清理和业务记录删除保持在受保护的操作中。
- 删除前确认跨进程执行权已释放，防止取消后的在途执行与清理竞争；统一服务层删除入口的保护。
- 回归覆盖排队 pending、启动与删除竞争、删除拒绝无清理副作用，以及取消停止后的文件、结果和额度一致性。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/evaluation-execution`：补充评估删除的任务活动状态、事务互斥、执行停止和资源清理约束。

## Impact

- 主要实现范围：`api/services/evaluation_service.py`、`src/task_manager.py`；复用现有文件清理及执行锁机制。
- 测试范围：评估服务/操作能力、并发提交及 HTTP 文件删除相关回归，预计最多 6 个交付文件。
- API 地址与响应结构保持现有契约；已入队 pending 评估的删除请求改为拒绝。
- 不新增数据库 schema 或依赖，不修复历史孤立任务，不调用付费模型。
