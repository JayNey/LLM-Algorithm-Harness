## Why

用户授权先完成 #157 已具备条件的部分，并继续更新 PR #174。#148/#152/#153/#151 已合并；最新 main 引入 SQLAlchemy 持久化任务，原监控快照已不兼容。#149 队列仍未完成，需要对接真实业务数据库并保留明确的队列接入边界。

## What Changes

- 服务端管理员用户 ID 白名单，保护系统监控与全局日志。
- 当前 SQLite、Docker 预检、资源、API 统计、任务状态与配置查询。
- 持久化脱敏日志、级别/时间/搜索/分页与所有者限定下载。
- 当前已实际执行的存储、并发和请求窗口配额查询。
- 复用运行中的业务数据库 engine，查询连通性、迁移版本和持久化任务，采集真实 SQL 查询耗时/错误；保留有限窗口与完整性说明。
- 未配置 Redis、worker 和真实 LLM 指标返回明确状态及空值。
- 统一修正现有 Docker 预检把 timeout/错误答案判为成功的问题。

## Capabilities

### New Capabilities
- `api/monitoring-foundation`: 系统监控、日志和当前配额的可用基础。

### Modified Capabilities
- `sandbox-preflight`: 最小预检必须成功完成且用例通过，避免失败后报告健康。

## Impact

新增 `api/monitoring/` 与路由，集成现有 ASGI 日志、身份和审计。新增 psutil 依赖及独立 SQLite 表；兼容 #151 的 SQLAlchemy 与 Alembic。此次 PR 仅关联 #157，不关闭整个 issue；队列/真实 worker/LLM/容器指标仍等待后续接入。
