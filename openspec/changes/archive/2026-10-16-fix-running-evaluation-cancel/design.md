## Context

见 `proposal.md`。评估 worker 使用 `TaskService(root=f"data/tasks/{evaluation_id}")`，运行标识为 `eval-{evaluation_id}`。`TaskService.request_cancel` 会把检查点上的 `cancel_requested` 写成真，`run()` 在每个单元边界重新读取该标记并停止后续派发。`TaskManager.cancel_task` 目前只 revoke Celery 任务并提交 `cancelled`。评估收尾按检查点状态写回数据库，检查点为 `completed` 时会覆盖调用方已经写下的 `cancelled`。

真实 worker 集成测试在独立进程中执行 `run_evaluation_task`。当前执行器在任何单元之前解析模型和凭证；测试种子两者都没有。

## Goals / Non-Goals

**Goals:**

- 运行中的评估取消能在单元边界停住，并保持 `cancelled`。
- 尚未生成检查点的取消仍 revoke Celery 任务并保持 `cancelled`。
- 真实 worker 集成测试按当前执行器的起步条件准备数据，并在不访问外部模型和沙箱的前提下跑完编排。

**Non-Goals:**

- 不改变实验、导入、基准测试的暂停或恢复。
- 不移除 Celery revoke。
- 不让集成测试访问真实模型或启动沙箱。

## Decisions

1. **取消评估时请求同一份检查点的协作式取消。** `TaskManager.cancel_task` 在任务类型为 `evaluation` 时，用与 worker 相同的根目录和运行标识调用 `TaskService.request_cancel`。检查点尚不存在时忽略缺失，仍 revoke 并把数据库写成 `cancelled`。这样 API 进程写入的标记能被 worker 下一轮循环读到。备选是只在 worker 里轮询数据库的 `cancelled`：能避免覆盖，但不能把尚未派发的单元标成取消，`TaskService` 已有的取消协议也不会生效。

2. **worker 在起步和收尾都尊重已取消状态。** 加载任务后若数据库状态已是 `cancelled`，直接返回，不创建执行。`run()` 返回后重新读取任务；若状态已是 `cancelled`，评估也保持 `cancelled`，不用检查点的 `completed`、`paused` 或 `failed` 覆盖。已经开始的单元允许做完。

3. **集成测试只替换 worker 进程内的外部边界。** 完成用例改为使用测试专用 Celery 入口。该入口在导入任务后替换凭证解析、策略 runtime 预检、题目执行和成本估算。种子评估写入 `model`、`api_key_id` 和可解析的题目行，使真实的起步校验得以通过。父进程的 monkeypatch 进不了 worker 子进程，所以替身必须放在 worker 入口里。

## Risks / Trade-offs

- [API 与 worker 的工作目录不同，相对检查点路径不一致] → 取消使用与 worker 相同的 `data/tasks/{evaluation_id}` 相对路径；集成测试和本地 worker 都从仓库根启动。
- [取消发生在当前单元执行期间] → 该单元可以做完，后续单元不再派发；收尾以数据库中的 `cancelled` 为准。
- [worker 替身掩盖真实模型调用] → 替身只存在于该集成测试入口，生产任务模块不读取测试开关。
