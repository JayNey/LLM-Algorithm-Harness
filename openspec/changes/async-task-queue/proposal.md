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
