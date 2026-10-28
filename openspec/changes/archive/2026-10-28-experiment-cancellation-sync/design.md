## Context

参见 proposal.md。取消目前仅同步 A/B；实验 Worker 直接写 running，服务层只检查暂停，通用状态更新和 Celery 回填可覆盖取消。SQLite 忽略 SELECT FOR UPDATE，单纯读取状态后保存不能消除竞争。

## Goals / Non-Goals

在现有实验生命周期内同步状态和时间、保持终态并验证所有者；不扩展其他任务类型的生命周期，不改变删除规则，不新增公开端点或 schema。

## Decisions

- 所有实验状态迁移先通过 AsyncTask 的无值变化 UPDATE 取得写锁并刷新对象，再检查状态与更新 Experiment；SQLite 和 PostgreSQL 使用一致的 task → experiment 锁顺序，事务内双写。避免使用进程内锁或 SQLite 不支持的行级 FOR UPDATE。
- 任务管理的实验状态更新保护 cancelled/completed/failed，paused 仅允许取消；启动、暂停、取消和终态通过相同同步逻辑处理。Celery STARTED/PROGRESS 不取代实验业务状态；失败/撤销按当前持久化状态处理。
- 服务收尾在相同任务锁下用带 owner/status 条件的 Experiment UPDATE 保存结果，随后同步任务；取消已先提交则不写结果或异常。没有关联任务的历史内部执行仍使用条件 UPDATE 保护终态。
- 复用 runner 的组合边界停止回调，把 cancelled 纳入停止条件；停止后保留取消状态，避免把取消解释为暂停。
- Worker 启动与回调重新读取持久化任务状态，取消或取消后删除均按 cancelled 返回。

## Risks / Trade-offs

- SQLite 写锁覆盖短状态事务，不能持有到模型执行结束；所有执行逻辑在提交后运行。
- 已经开始的组合可能做完，但不派发后续组合，晚到结果不修改取消状态。
- 真实模型及 broker 在回归测试中替身；数据库状态和并发事务使用真实 SQLite 文件及独立连接，静态检查 PostgreSQL 的一致锁顺序。

## Workflow Decision

用户 A2 已确认该跨模块范围继续 tweak、新分支；仅三处生产文件及两处测试文件，文档为必需 OpenSpec 产物。
