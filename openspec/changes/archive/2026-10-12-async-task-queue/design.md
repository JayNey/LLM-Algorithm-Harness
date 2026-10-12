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
