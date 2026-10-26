## Why
A/B 测试在 API daemon 线程中执行，不能使用统一任务管理，API 重启还会把独立执行中的任务误判失败。将执行迁移到已有 Celery 队列，使状态和生命周期可持久化追踪。

## What Changes
- A/B run 接口通过 TaskManager 先落库再发布，返回 task_id，worker 开始前保持 pending。
- 新增 A/B worker，统一成功、失败、暂停、取消与执行时间；重复提交和重复消息不重复执行。
- API 重启保留已排队与运行的任务；worker 内解析所有者密钥。
- 接入已有监控类型和生命周期日志，补充回归验证。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `async-task-queue`: 增加 A/B 异步执行和统一生命周期场景。
- `api/experiment-management`: A/B 运行返回可查询任务标识。

## Impact
涉及 A/B service、Celery worker/注册、TaskManager 的 A/B 状态同步、runner 停止检查、监控白名单及测试和 API 文档。复用现有数据库结构和队列，无新增依赖。
