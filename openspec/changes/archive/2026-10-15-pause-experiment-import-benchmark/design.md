## Context

见 `proposal.md`。`TaskManager.pause_task` 只把调用方自己的 `running` 任务写成 `paused`，不 revoke Celery。评估 worker 用另一条数据库连接上的 `populate_existing()` 读到这个状态，并在单元边界停止。实验、导入和基准 worker 没有这条检查，结束时调用 `update_task_status` 覆盖暂停。

## Goals / Non-Goals

**Goals:**

- 三类 worker 都能从另一条连接读到暂停。
- 暂停后不再开始新的组合、题目或基准问题。
- 任务和业务记录保持 `paused`。

**Non-Goals:**

- 不恢复这三类任务。恢复接口继续拒绝非评估任务。
- 不中断已经开始的单个组合、单个导入项或单个基准问题。
- 不改评估的暂停和恢复。

## Decisions

1. **沿用协作式暂停，不 revoke。** 与评估相同：暂停只写数据库，worker 在安全边界自己停止。备选是 pause 时 revoke Celery，那会丢掉进行中的单元，也和现有 `pause_task` 说明相反。

2. **安全边界按现有循环设置。** 实验在每个组合开始前检查；导入在每道题开始前以及写入数据集合并前检查；基准在每道题开始前检查。并行实验里已经提交的组合可以做完，未提交的不再开始。

3. **读暂停必须绕过 identity map。** worker 会话是 `expire_on_commit=False`。检查时对 `AsyncTask` 使用 `populate_existing()`，否则看不到 API 进程刚写入的 `paused`。

4. **结束写入不得覆盖暂停。** 执行函数返回后如果任务已是 `paused`，实验、导入作业和基准运行都写成 `paused`，并且不再调用会把任务改成 `completed` 或 `failed` 的更新。

## Risks / Trade-offs

- [暂停后不能从断点继续] → 恢复仍只接受评估。调用方可以取消已暂停的任务。
- [并行实验里已经提交的组合仍会跑完] → 与评估“不打断进行中的单元”一致，停止的是后续派发。

## Migration Plan

无数据迁移。回滚时三类 worker 恢复为结束后覆盖状态即可。已经停在 `paused` 的记录保持暂停，不会自动继续。
