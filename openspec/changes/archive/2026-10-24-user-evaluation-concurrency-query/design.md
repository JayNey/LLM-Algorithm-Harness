## 实现说明
从 MonitorService.task_engine 用单次 SELECT COUNT 读取当前认证用户 task_type=evaluation 且 status 为 pending/running 的 AsyncTask；不轮询 Celery、不修改任务、不关联 Evaluation（避免草稿误计）。limit 取 api.config.settings.MAX_CONCURRENT_EVALUATIONS_PER_USER，与 TaskManager 准入一致。remaining=max(limit-used,0)，超限历史数据保留真实 used。

现有两个路由复用同一查询，身份取认证主体，用户参数不得更改范围。查询是瞬时观测，不预留名额，任务变化后再次查询读取最新已提交状态。数据库错误沿用标准 API 错误处理，不伪造零用量。

## 验证
覆盖空库、自定义限额、pending/running、其他状态与类型、用户隔离、超限归零、状态变化及独立任务 engine。HTTP 验证两个别名的认证、身份参数不可越权与 no-store；同步 OpenAPI 示例和监控指南。
