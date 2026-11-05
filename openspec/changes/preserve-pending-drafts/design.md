## 实现说明
采用现有字段，无迁移。pending 且 started_at 为空、没有任务提交证据的记录是草稿；评估 async_task_id 非空或同 owner/type/entity 的历史任务，以及实验同 owner/type/entity 的历史任务，是提交证据。running 或有开始时间的记录也属于已执行记录。活跃 pending/running/paused 任务继续保护业务行，真正孤立执行保留现有 failed 策略。
恢复采用单条带相关 EXISTS 条件的 UPDATE，避免先读取候选再写回覆盖并发启动、创建或完成；不变更启动入口的唯一入队机制。benchmark 恢复语义不变。

## 验证
先复现草稿被错误置 failed，再覆盖真实创建后重建/第二实例、实际 start 唯一入队、重复恢复、started_at/失效关联/历史任务、活跃任务及终态。使用 SQLAlchemy 事件在恢复执行前提交启动/创建/终态变更以验证竞态。
