## Why
现有查询性能仅覆盖评估服务 engine，遗漏实验、基准、A/B、异步任务及认证/文件 SQLite，容易被误读为全量数据库统计。

## What Changes
- 接入当前 API 实例全部业务 engine，并为认证/文件共享 SQLite 增加执行采集。
- 保留 database_queries 顶层评估口径兼容性，新增 sources 列表，逐项标明 backend、roles、数据源标识和当前进程范围；不合并不同来源百分位。
- 保持有界内存、缺口语义、原异常及隐私边界。

## Capabilities
### New Capabilities
- `api/database-query-metrics`: 将已有查询性能能力的完整采集范围固化为规格。
### Modified Capabilities
无。

## Impact
监控采集器、AuthStore SQLite 连接工厂、MonitorService 和应用启动装配、回归测试及监控文档；无数据库 schema、依赖或新端点。用户明确指定新分支、继续 tweak、完成后归档并推送，沿用该授权。
