## Why

API 重启会把独立 Celery worker 仍在执行的评估、实验和基准记录误标为 `failed`。实验 worker 随后因记录已不处于 `running` 而跳过完成回写，导致产物目录及完成时间无法关联到实验。

## 根因分析

三个服务的 `_recover_interrupted` 都只保护关联活跃 AsyncTask 的 `pending` 记录，未保护 `running` 记录。API 进程重启不代表独立 worker 中断；实验和基准正常完成时的状态守卫会拒绝覆盖误写的失败状态。

## What Changes

- 启动恢复保护关联活跃异步任务的 `pending` 和 `running` 业务记录，统一将 `pending/running/paused` 视为活跃任务。
- 无活跃异步任务的遗留在途记录继续按原有语义标记失败，终态与暂停记录保持不变。
- 回归验证 API 启动不干扰 worker 执行，以及实验完成后的产物目录、完成时间和结果查询。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `async-task-queue`：补充 API 重启保护正在执行的异步评估、实验和基准的验收场景。

## Impact

仅修改 `api/services/` 中三个恢复条件及一个回归测试文件。无新增 capability、public API、数据库 schema 或架构变更，无跨模块协调修改；worker 的正常收尾守卫保持原样。用户选择新建分支 `hotfix/20261022/fix-api-restart-worker-recovery`。
