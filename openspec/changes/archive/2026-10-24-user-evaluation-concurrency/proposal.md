## Why

评估提交没有按用户执行并发配额，多 API 进程和 worker 会共享队列，却无法通过进程内信号量限制同一用户占用。

## What Changes

- 增加正整数配置 `MAX_CONCURRENT_EVALUATIONS_PER_USER`，默认 5。
- 在评估入队事务中按用户原子检查共享业务库中的 pending/running 任务；超限拒绝且不发布消息。
- 覆盖启动、异步创建和暂停/失败后的恢复；暂停和终态不占用准入额度。
- 超限启动返回 HTTP 429，其他用户保有独立额度。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/evaluation-execution`：增加评估提交阶段的按用户并发准入要求。

## Impact

仅涉及 API 配置、TaskManager 评估提交分支、评估错误映射、测试与说明文档。复用现有任务表和事务，不增加 schema、公共端点或服务依赖。
