## Why

取消一个正在执行的评估时，接口只把数据库写成 `cancelled` 并向 Celery 发终止信号。执行循环不读取这个状态，也不请求 `TaskService` 的协作式取消；任务若在进程退出前跑完，收尾会把 `cancelled` 盖回 `completed`。与此同时，真实 worker 集成测试仍按已经删除的模拟执行器准备数据，种子评估没有模型和凭证，当前执行器会在起步时失败，测试却等待 `completed`。

## What Changes

- 取消正在执行的评估时，除 revoke Celery 任务外，请求 `TaskService` 协作式取消；worker 在下一个尚未开始的单元前停止派发，收尾不得把已取消的评估写成 `completed`。
- 修正真实 worker 集成测试：按当前执行器的起步条件准备评估，并只在 worker 进程里替换对外的模型调用和沙箱预检，使任务能走完真实编排并变为 `completed`。

## Capabilities

### New Capabilities

### Modified Capabilities

- `async-task-queue`: 取消正在执行的评估时，worker 在单元边界停止后续派发，且最终状态保持 `cancelled`。

## Impact

- `src/task_manager.py`：评估取消同时请求协作式取消。
- `src/tasks/evaluation.py`：收尾前确认任务未被取消，避免覆盖 `cancelled`。
- `tests/test_async_task_integration.py`：种子数据与 worker 侧外部依赖替身对齐当前执行器。
- `tests/test_task_manager.py`、`tests/test_celery_tasks.py`：覆盖运行中取消不再完成。
