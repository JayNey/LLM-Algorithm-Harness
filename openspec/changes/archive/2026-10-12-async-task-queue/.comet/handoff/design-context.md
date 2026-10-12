# Comet Design Handoff

- Change: async-task-queue
- Phase: design
- Mode: compact
- Context hash: 69bdbf9748cea4b985cbffe501815da35f60eb631e7b2d161b52ca2b9a181fe2

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/async-task-queue/proposal.md

- Source: openspec/changes/async-task-queue/proposal.md
- Lines: 1-37
- SHA256: b1e34cc4db77ac965a11269ae714b3bb9d55166685e3ebb02d07286b49b69605

```md
## Why

当前的评估任务可能运行数分钟到数小时，直接在 API 请求中执行会导致超时和阻塞。需要实现异步任务队列系统，将长时间运行的评估任务从 API 请求中解耦，提供非阻塞的任务提交、状态查询和管理功能。

## What Changes

- 集成 Celery 作为分布式任务队列框架，使用 Redis 作为消息代理和结果后端
- 将现有的 CLI 评估功能（evaluation、experiment、import、benchmark）封装为 Celery 异步任务
- 提供 RESTful API 端点用于创建任务、查询状态、取消任务、暂停/恢复任务
- 任务结果持久化到数据库，支持任务历史记录查询和清理
- 保持与现有 `TaskService` 和 `--resume` 功能的兼容性

## Capabilities

### New Capabilities
- `api/async-task-queue`: 异步任务队列的核心功能，包括 Celery worker 配置、任务定义、任务状态管理和 API 端点

### Modified Capabilities
- `api/database-schema`: 需要新增 `async_tasks` 表用于持久化任务元数据和状态

## Impact

**新增依赖**：
- Celery 5.x（任务队列框架）
- Redis（消息代理和结果后端）
- 可选：Flower（任务监控 UI）

**影响的代码模块**：
- `src/task_service.py`：现有任务服务将被 Celery 任务调用，作为底层执行引擎
- `src/main.py`：CLI 命令将继续可用，但内部实现需要支持异步任务创建
- `src/api/`：新增任务管理相关的 API 路由和端点
- 数据库 schema：新增 `async_tasks` 表

**部署影响**：
- 需要运行独立的 Celery worker 进程
- 需要部署 Redis 服务
- 需要配置 Celery broker 和 result backend URL

```

## openspec/changes/async-task-queue/design.md

- Source: openspec/changes/async-task-queue/design.md
- Lines: 1-59
- SHA256: 89541cafaa9518b74aff13adddba6d0600b10718695bf60417583f85411ced56

```md
## 实现方案

### 架构概览

```
API 请求 → FastAPI 端点 → Celery Task → TaskService → 评估执行器
                                ↓
                            Redis (broker + result backend)
                                ↓
                        数据库 (async_tasks 表)
```

### 核心组件

#### 1. Celery 配置
- 使用 Redis 作为 broker 和 result backend
- Worker 配置：支持并发执行，使用 prefork 或 gevent pool
- 任务路由：所有评估任务路由到同一队列

#### 2. 任务定义
封装现有 CLI 功能为 Celery 任务：
- `run_evaluation_task(config, dataset_path, run_id)`
- `run_experiment_task(config, experiment_spec, run_id)`
- `run_import_task(source, dataset_path)`
- `run_benchmark_task(config, benchmark_spec, run_id)`

每个任务内部调用现有的 `TaskService`，保持业务逻辑不变。

#### 3. 数据库扩展
新增 `async_tasks` 表：
- `task_id` (主键): Celery task ID
- `task_type`: 任务类型（evaluation/experiment/import/benchmark）
- `user_id`: 用户标识
- `run_id`: 对应 TaskService 的 run_id
- `status`: 任务状态（pending/running/success/failed/cancelled）
- `progress`: 进度百分比
- `created_at`, `started_at`, `finished_at`
- `error_message`: 失败原因
- `result_summary`: 任务结果摘要

#### 4. API 端点
- `POST /api/v1/tasks`: 创建任务，参数验证后提交到 Celery
- `GET /api/v1/tasks/{task_id}`: 查询任务状态，聚合 Celery 状态和数据库记录
- `DELETE /api/v1/tasks/{task_id}`: 取消任务，调用 Celery revoke 并标记数据库
- `POST /api/v1/tasks/{task_id}/pause`: 利用 TaskService 的暂停机制
- `POST /api/v1/tasks/{task_id}/resume`: 利用 TaskService 的恢复功能
- `GET /api/v1/tasks`: 列出任务，分页查询数据库

### 兼容性保持

- CLI 命令保持原有接口，可选择同步执行或创建异步任务
- `TaskService` 作为执行引擎，不改变其核心逻辑
- `--run-id` 和 `--resume` 功能继续工作，映射到 Celery 任务的恢复机制

### 部署要求

- Redis 服务（推荐 6.0+）
- Celery worker 启动命令：`celery -A src.celery_app worker --loglevel=info`
- 可选：Flower 监控服务：`celery -A src.celery_app flower`

```

## openspec/changes/async-task-queue/tasks.md

- Source: openspec/changes/async-task-queue/tasks.md
- Lines: 1-49
- SHA256: 9b0aa570c0bdaf44e61a87a31210adfbcf6a8f6cee94109abc713de3edf16de8

```md
# 任务清单

## 1. Celery 基础设施
- [ ] 安装依赖：celery[redis], redis
- [ ] 创建 `src/celery_app.py` 配置 Celery 应用
- [ ] 配置 Redis broker 和 result backend
- [ ] 添加环境变量配置（CELERY_BROKER_URL, CELERY_RESULT_BACKEND）

## 2. 数据库扩展
- [ ] 创建 `async_tasks` 表的 SQLAlchemy model
- [ ] 生成 Alembic migration
- [ ] 执行数据库迁移

## 3. Celery 任务定义
- [ ] 实现 `run_evaluation_task` Celery 任务
- [ ] 实现 `run_experiment_task` Celery 任务
- [ ] 实现 `run_import_task` Celery 任务
- [ ] 实现 `run_benchmark_task` Celery 任务
- [ ] 添加任务进度报告机制（update_state）

## 4. API 端点实现
- [ ] 创建 `src/api/routers/tasks.py` 路由模块
- [ ] 实现 `POST /api/v1/tasks` 创建任务端点
- [ ] 实现 `GET /api/v1/tasks/{task_id}` 查询状态端点
- [ ] 实现 `DELETE /api/v1/tasks/{task_id}` 取消任务端点
- [ ] 实现 `POST /api/v1/tasks/{task_id}/pause` 暂停端点
- [ ] 实现 `POST /api/v1/tasks/{task_id}/resume` 恢复端点
- [ ] 实现 `GET /api/v1/tasks` 列表查询端点
- [ ] 在主 FastAPI 应用中注册路由

## 5. 任务服务集成
- [ ] 修改 TaskService 调用，使其能在 Celery worker 进程中运行
- [ ] 实现任务结果持久化到 `async_tasks` 表
- [ ] 实现错误处理和重试逻辑

## 6. CLI 集成（可选）
- [ ] 为 CLI 命令添加 `--async` 参数
- [ ] 当使用 `--async` 时，创建 Celery 任务而非同步执行

## 7. 测试
- [ ] 单元测试：Celery 任务定义
- [ ] 单元测试：API 端点
- [ ] 集成测试：完整的异步任务执行流程
- [ ] 测试取消和暂停/恢复功能

## 8. 文档
- [ ] 更新 README：添加 Celery worker 启动说明
- [ ] 更新 API 文档：新增任务管理端点
- [ ] 添加部署指南：Redis 和 Celery worker 配置

```
