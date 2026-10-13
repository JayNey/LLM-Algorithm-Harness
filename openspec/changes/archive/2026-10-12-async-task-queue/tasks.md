# 任务清单

## 任务 1：Celery 基础设施搭建
- [x] 安装依赖：celery[redis], redis
- [x] 创建 `src/celery_app.py` 配置 Celery 应用
- [x] 配置 Redis broker 和 result backend
- [x] 添加环境变量配置（CELERY_BROKER_URL, CELERY_RESULT_BACKEND）

## 2. 数据库扩展
- [x] 创建 `async_tasks` 表的 SQLAlchemy model
- [x] 生成 Alembic migration
- [x] 执行数据库迁移

## 3. Celery 任务定义
- [x] 实现 `run_evaluation_task` Celery 任务
- [x] 实现 `run_experiment_task` Celery 任务
- [x] 实现 `run_import_task` Celery 任务
- [x] 实现 `run_benchmark_task` Celery 任务
- [x] 添加任务进度报告机制（update_state）

## 4. EvaluationService 改造（Task 5）
- [x] 添加 ProgressInfo schema 支持 current/total/message
- [x] 修改 EvaluationResponse 添加 progress 字段
- [x] 改造 create_evaluation 提交 Celery 任务
- [x] 改造 get_evaluation 聚合 AsyncTask 状态
- [x] 实现 pause_evaluation 暂停任务
- [x] 实现 resume_evaluation 恢复任务
- [x] 实现 delete_evaluation 包含任务取消
- [x] 实现完整的 TDD 测试套件

## 5. API 端点实现（Task 6）
- [x] 创建 `api/routes/tasks.py` 路由模块
- [x] 实现 `POST /api/v1/tasks` 创建任务端点
- [x] 实现 `GET /api/v1/tasks/{task_id}` 查询状态端点
- [x] 实现 `DELETE /api/v1/tasks/{task_id}` 取消任务端点
- [x] 实现 `POST /api/v1/tasks/{task_id}/pause` 暂停端点
- [x] 实现 `POST /api/v1/tasks/{task_id}/resume` 恢复端点
- [x] 实现 `GET /api/v1/tasks` 列表查询端点
- [x] 在主 FastAPI 应用中注册路由
- [x] 创建 API 端点测试（15 个测试全部通过）

## 6. 集成测试（Task 7）
- [x] 创建集成测试框架 `tests/test_evaluation_async_flow.py`
- [x] 测试创建和轮询流程
- [x] 测试暂停和恢复功能
- [x] 测试任务列表和过滤
- [x] 测试错误场景和权限控制
- [x] 测试无效状态转换
- [x] 测试进度信息更新
- [x] 22 个集成测试全部通过

## 7. 文档更新（Task 8）
- [x] 更新 README：添加异步任务队列章节
- [x] 添加启动说明（Redis、Worker、API、Flower）
- [x] 创建部署指南：docs/deployment/async-tasks.md
- [x] 生产环境部署配置（Systemd、Nginx、监控）
- [x] 故障排查手册
- [x] 性能优化建议

## 8. 任务清理功能（Task 9）
- [x] 实现 cleanup_old_tasks Celery 任务
- [x] 实现 cleanup_task_count 基于容量的清理策略
- [x] 配置 Celery Beat 定时调度
- [x] 添加清理功能单元测试（5 个测试全部通过）
- [x] 部署指南中添加清理配置说明
