# 任务清单

## 任务 1：Celery 基础设施搭建
- [x] 安装依赖：celery[redis], redis
- [x] 创建 `src/celery_app.py` 配置 Celery 应用
- [x] 配置 Redis broker 和 result backend
- [x] 添加环境变量配置（CELERY_BROKER_URL, CELERY_RESULT_BACKEND）

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
