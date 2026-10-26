## 实现方案
沿用现有 TaskManager.enqueue_task 和 default 队列。AsyncTask 以 task_type=ab_test、entity_id 和 user_id 关联业务记录，无需 schema 迁移。run 返回 task_id；详情从持久化关联中返回同一标识。

启动时在业务记录上取得写锁，再检查已有任务，保证并发启动最多发布一次。任务记录必须先提交再发布；发布失败仅将仍 pending 的两层状态同步为 failed，不覆盖发布期间已取消、已完成或已开始的任务。worker 以 pending → running 条件更新原子领取任务，验证业务所有者与 Celery 消息标识，重复投递及终态任务直接跳过。

worker 以 recover=False 创建 A/B service，在原子领取任务后创建 AuthService 并构造含密钥配置。A/B 单独设置 reject_on_worker_lost=False，Celery 父进程检测到 WorkerLostError 后通过 task_failure 信号将未结束任务与业务记录同步为 failed；正常重复消息仍跳过，不根据 redelivered 推断原 worker 是否存活。失败信号严格匹配所有者、实体和消息 ID，不覆盖暂停或终态。每次投递由父进程 Request 生成唯一 execution_attempt，经请求上下文传给子进程并随原子领取写入已有 progress JSON；父进程仅终结该 attempt 持有的 running 任务，重复消息的未领取 child 丢失不会误伤原执行。service 执行前和结束时在同一事务内更新两层状态与时间。异常保留失败原因；暂停和取消通过 TaskManager 同步业务记录。runner 在题目边界读取停止信号，已开始单元可以完成，停止后不写最终报告，收尾不覆盖暂停/取消状态。暂不增加 A/B 恢复功能，沿用统一接口仅支持评估恢复的约束。

API 启动不改变有活跃任务关联的记录；未入队的 pending 配置仍可启动。仅没有活跃关联的遗留 running 记录标为中断。TaskManager 同步 Celery 失败/撤销状态时也同步 A/B 记录。删除前拒绝活跃任务，终态删除清理关联记录。

前端保留 nullable task_id，排队时显示等待提示并禁用重复启动和删除；沿用已有布局、轮询与状态展示。

## 验证
使用真实临时数据库验证发布前提交、并发启动、worker 成功/失败、跨用户、重复投递、暂停/取消、重启保护、结果读取及监控分类；外部 broker 和模型调用由测试替身隔离。运行相关回归、格式/静态检查及编译。

## 用户决策
用户回复 A+D：继续 tweak，使用新分支。已确认本次跨模块协调，预期超过六个文件，仍采用现有架构完成单一 change。
