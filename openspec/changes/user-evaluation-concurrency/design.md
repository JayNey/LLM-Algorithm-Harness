## Context

评估通过 TaskManager 的 create_task/enqueue_task 提交，API 启动和异步创建使用后者，恢复使用前者。业务库支持 SQLite 与 PostgreSQL，用户身份在独立认证库中。

## Decisions

- 在两种 TaskManager 提交入口、创建候选 AsyncTask 前统一执行评估准入。统计该 user_id 的 evaluation 类型 pending/running 行，草稿无 AsyncTask，不计入；暂停、失败、取消、完成后自动释放逻辑额度。计数包括未关联的已提交任务，避免遗漏正在恢复的任务。
- SQLite 在读取计数前执行无匹配行 UPDATE 获取数据库写锁；PostgreSQL 使用稳定用户标识哈希的事务级 advisory lock。锁与候选任务写入同一事务，提交/回滚自动释放；不依赖进程锁或 Redis 可用性。锁等待失败保持失败关闭，不发布消息。
- `MAX_CONCURRENT_EVALUATIONS_PER_USER` 默认 5，必须为正整数；部署中的提交进程应共享业务库并使用一致配置。
- 超限抛出专用 ValueError 子类；现有评估路由映射 HTTP 429。不新增端点或修改数据库结构。
- 准入上限限制持久化 pending/running 评估任务数量，不改变既有暂停/取消的单元边界停止语义，亦不增加 worker 重投递去重协议。

## Risks / Trade-offs

- SQLite 写锁串行化短事务；生产 PostgreSQL 按用户串行化，避免全局锁。
- pending 纳入额度会限制队列积压；这是提交时预留容量以保证 worker 总准入量的必要语义。
- 宕机遗留 pending/running 记录保守占用额度，沿用现有状态恢复处理，不以过期租约冒险释放仍在运行的任务。
- 发布失败的 enqueue_task 会标记 failed 并释放额度；create_task 原有发布异常通过调用方回滚释放。

## Validation

先以真实 SQLite 记录证明现有代码超限仍入队。验证用户隔离、不同状态、启动/恢复/异步创建、发布失败及回滚、真实多进程独立连接竞争、API 429。PostgreSQL 使用可用真实环境时执行集成测试；无环境时报告该限制，并验证所发锁语句与绑定参数。
