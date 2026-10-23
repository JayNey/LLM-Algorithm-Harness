## Why
真实 Celery worker 的执行事件尚未进入持久化日志，现有查询与下载只校验旧 run 映射，无法查看业务异步任务的执行过程。

## What Changes
- 接入四类异步任务生命周期、数值进度以及评估逐单元事件。
- 查询和下载通过真实 AsyncTask 所有者鉴权，兼容旧评估运行日志。
- 事件入库前脱敏，仅保留允许的结构化字段；记录失败不改变任务结果。
- 验证权限、过滤、分页、下载、跨进程持久化与故障降级。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `async-task-queue`: 增加真实执行日志的采集、隔离与读取契约。

## Impact
涉及 TaskManager、worker/服务进度回调、监控日志解析及 API 文档和测试。复用现有 SQLite 日志表，无 schema 迁移或新外部依赖。2026-10-23 用户已选择独立分支并确认跨模块范围继续 tweak；预计实现、测试与产物超过 6 文件，此范围沿用该确认。
