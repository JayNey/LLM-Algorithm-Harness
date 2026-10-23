## Context
现有 MonitorStore 提供有界保留、脱敏、查询、过滤和 JSONL 导出。worker 通过 TaskManager 更新生命周期，其他进度直接提交业务会话；旧日志权限依赖 FileStore 的 run 映射。

## Goals / Non-Goals
完成真实队列执行日志与现有 API 的接入。保留现有查询参数与旧 run 行为；本次不新增前端页面、日志基础设施或 schema。

## Decisions
- 生命周期在 TaskManager 提交成功后记录，进度在各实际 worker/服务提交点记录，评估另记录单元开始与结束。固定事件名，失败等级为 ERROR；拒绝原始异常、代码、题目正文和请求参数进入事件。
- writer 延迟构建 AuthService/MonitorStore，只复用现有认证数据库；每次操作独立连接，API 和 worker 必须使用同一 AUTH_DATABASE_PATH（现有 compose 共用 data）。已保存密钥和服务端密钥用于入库前脱敏，字段白名单减少敏感载荷。
- 以 AsyncTask.id 为规范日志归属，内部使用 async: 前缀隔离旧 run 日志。API 先解析真实 AsyncTask，再解析关联 Evaluation，最后兼容旧映射；命中但不属于用户即 404，不回退。关联评估必须匹配 owner/type/entity，查询不轮询 Celery。
- 日志写入 best-effort，失败仅输出固定警告，不传播原始异常或损坏业务会话。保留上限沿用 MonitorSettings；不承诺崩溃前最后一次事件或 exactly-once（重投递可产生重复执行事件）。

## Risks / Trade-offs
日志和业务提交不在同一事务，进程崩溃可留下缺口；通过明确保留日志语义和故障测试避免假称完整。共享 SQLite 的部署需要共用路径；跨主机独立磁盘部署需另行集中日志存储。

## Migration Plan
无需迁移。部署 API/worker 使用相同版本与共享认证数据库；旧日志保持可读。回滚代码即可停止新增事件。
