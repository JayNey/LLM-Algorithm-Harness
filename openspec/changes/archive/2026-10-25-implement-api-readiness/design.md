## Context

MonitorProbes.database() 已检查认证、文件与业务库的连接、表与 Alembic revision。诊断开关不应阻止基础数据库就绪探测。

## Decisions

公开接口返回 {"status":"ready"} 或 {"status":"not_ready"}，HTTP 200/503，no-store。必需组件及业务迁移均须 ok；未知、异常、超时均失败关闭，不暴露详情。队列、worker、沙箱不参与。

ReadinessCheck 每个 MonitorService 实例持有独立缓存与锁。异步路由在入口建立绝对 deadline，绕过业务 AnyIO 线程池，在独立 asyncio 执行器中等待；排队和探测共用该 deadline，使用单调时钟，探测响应预算 1 秒，成功和失败缓存均 1 秒。后台 daemon 线程最多一个，超时不能中断同步数据库调用，迟到结果丢弃；线程仍运行时不再启动新探测，避免资源堆积。进程退出不等待被阻塞线程。此限制写入文档。

## Verification

先测试 HTTP 缺失，再覆盖真实数据库成功、缺表、迁移不匹配、依赖不参与、异常脱敏、缓存失效、并发合并、超时与迟到结果、实例隔离。运行相关监控与 API 契约回归、ruff/black、compileall。tweak 无独立 Design Doc。
