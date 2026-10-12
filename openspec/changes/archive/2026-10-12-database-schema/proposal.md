## Why

Issue #151 要求为 Web 后端设计并实现数据库 schema。当前评估任务保存在进程内存（`api/services/evaluation_service.py` 的 `TaskState`，重启即丢失），题库散落在 JSON 文件中。#171 REST API 与 #172 认证合并后，#149 任务队列、#150 进度推送、#155 结果查询、#156 实验管理都以持久化为前置依赖。

## What Changes

- 新增 SQLAlchemy 2.x 业务数据库层（`api/db/`）与 Alembic 迁移。
- 核心业务表：`problems`、`evaluations`、`evaluation_results`（对应 issue 的 results 表；`users` 由 #172 的认证存储承担，不跨库重复建模）。
- 评估服务持久化改造：任务创建/状态/进度落库，服务重启后任务可查询，中断任务标记为 failed 并记录原因。
- 题库持久化：`problems` 表 + 现有 JSON 数据集的幂等导入。
- 配置注入 `DATABASE_URL`：开发/测试默认 SQLite，生产可切换 PostgreSQL（部署配置由 #159 交付）。

## Capabilities

### New Capabilities
- `api/database-schema`: 业务数据的关系型持久化、迁移管理与题库入库。

### Modified Capabilities
无。

## Impact

影响 `api/`（新增 db 包、改造 evaluation_service、配置项）与依赖声明（sqlalchemy、alembic）。认证存储（`api/auth/store.py`）保持物理隔离，不修改。CLI 行为不变。#149/#150/#155/#156 在本 change 之上构建。
