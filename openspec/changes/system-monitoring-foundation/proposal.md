## Why

用户授权继续更新 PR #174，使其兼容新 main。#148/#152/#153/#151 已合并；#179 已加入 Celery/Redis 和 AsyncTask 基础，#180 已加入实验/导入/基准任务入口。但 evaluation worker 仍模拟，其他任务入口不证明端到端执行或真实 LLM 指标可用，#149 尚未完整完成。监控应保留主线会话工厂生命周期与任务路由，区分旧评估和异步任务，不虚报真实执行或网络可用性。

## What Changes

- 服务端管理员用户 ID 白名单，保护系统监控与全局日志。
- 当前 SQLite、Docker 预检、资源、API 统计、任务状态与配置查询。
- 持久化脱敏日志、级别/时间/搜索/分页与所有者限定下载。
- 当前已实际执行的存储、并发和请求窗口配额查询。
- 复用运行中的业务数据库 engine，查询连通性、迁移版本和持久化任务，采集真实 SQL 查询耗时/错误；保留有限窗口与完整性说明。
- 按来源读取 legacy Evaluation / AsyncTask，排除旧评估中的异步关联记录以防重复计数；仅输出校验后的进度数值，不轮询 Redis 或提交任务状态。
- 已存在但未联网探测的 Redis/worker 返回 not_checked；未采集的真实 LLM 指标返回明确状态及空值。
- 统一修正现有 Docker 预检把 timeout/错误答案判为成功的问题。

## Capabilities

### New Capabilities
- `api/monitoring-foundation`: 系统监控、日志和当前配额的可用基础。

### Modified Capabilities
- `sandbox-preflight`: 最小预检必须成功完成且用例通过，避免失败后报告健康。

## Impact

新增 `api/monitoring/` 与路由，集成现有 ASGI 日志、身份和审计。新增 psutil 依赖及独立 SQLite 表；兼容 #151 的 SQLAlchemy 与 Alembic。此次 PR 仅关联 #157，不关闭整个 issue；队列/真实 worker/LLM/容器指标仍等待后续接入。
