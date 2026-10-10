## 1. 项目结构和依赖设置

- [x] 1.1 创建 `api/` 目录结构（`__init__.py`、`main.py`、`middleware/`、`routes/`、`services/` 等）并验证文件树符合设计文档
- [x] 1.2 添加 FastAPI、uvicorn、pydantic 依赖到 `requirements.txt`，运行 `pip install -r requirements.txt` 验证安装成功
- [x] 1.3 创建 `api/models.py` 定义 API 特定的请求/响应模型，验证 Pydantic 验证有效

## 2. FastAPI 基础框架

- [x] 2.1 在 `api/main.py` 创建 FastAPI 应用实例，配置 CORS 中间件，验证应用初始化无错误
- [x] 2.2 实现日志中间件记录请求/响应，运行应用并检查日志输出
- [x] 2.3 实现全局错误处理器，验证返回统一的错误格式

## 3. 通用端点

- [x] 3.1 实现 `/api/v1/health` 端点返回系统健康状态，运行 `curl http://localhost:8000/api/v1/health` 验证响应
- [x] 3.2 验证 `/docs` Swagger UI 和 `/openapi.json` 自动生成，在浏览器中访问 `/docs` 确认接口文档可用

## 4. 数据模型和适配层

- [x] 4.1 创建 `api/schemas.py` 定义统一的 API 响应包装器（`ApiResponse<T>`）和分页模型，编写单元测试验证序列化
- [x] 4.2 在 `api/services/` 创建服务适配层，将 `src/harness.py` 和 `src/models.py` 的业务逻辑包装为 API 友好的接口，编写集成测试验证数据映射正确

## 5. 评估任务管理端点

- [x] 5.1 实现 `POST /api/v1/evaluations` 创建评估任务，接受题目 ID 列表和策略配置，验证端点返回 201 和新任务 ID
- [x] 5.2 实现 `GET /api/v1/evaluations` 列出所有任务（支持分页和按状态过滤），验证返回分页数据和正确的过滤结果
- [x] 5.3 实现 `GET /api/v1/evaluations/{evaluation_id}` 获取单个任务详情，验证返回完整任务信息和进度数据
- [x] 5.4 实现 `PATCH /api/v1/evaluations/{evaluation_id}` 更新任务配置（仅 pending 状态可修改），验证更新成功且运行中任务被拒绝
- [x] 5.5 实现 `DELETE /api/v1/evaluations/{evaluation_id}` 删除任务（仅 pending 或 completed 可删除），验证删除成功且运行中任务被拒绝

## 6. 异步任务执行

- [x] 6.1 实现 `POST /api/v1/evaluations/{evaluation_id}/start` 启动任务，在后台线程中运行评估，验证立即返回 202 且任务开始执行
- [x] 6.2 实现 `GET /api/v1/evaluations/{evaluation_id}/progress` 获取实时进度，验证返回已完成数、总数和完成百分比
- [x] 6.3 实现 `POST /api/v1/evaluations/{evaluation_id}/cancel` 取消运行中的任务，验证任务状态变更为 cancelled 且停止执行
- [x] 6.4 实现任务并发限制（最多 5 个并发），超出时任务队列等待，编写测试验证并发限制有效

## 7. 其他端点（可选，第 2 阶段 - DEFERRED）

- [x] 7.1 实现 `GET /api/v1/problems` 问题列表端点（可选），验证返回所有可用问题 **DEFERRED to Phase 2**
- [x] 7.2 实现 `GET /api/v1/strategies` 策略列表端点（可选），验证返回所有支持的策略 **DEFERRED to Phase 2**

## 8. 测试和验证

- [x] 8.1 编写单元测试覆盖数据模型验证、错误处理和服务适配层，运行 `pytest tests/unit/` 验证全部通过
- [x] 8.2 编写集成测试覆盖完整的评估工作流（创建 → 启动 → 监控进度 → 完成），运行 `pytest tests/integration/` 验证通过
- [x] 8.3 手动测试所有端点使用 Swagger UI，验证请求和响应格式正确、错误处理表现正确
- [x] 8.4 性能测试验证并发请求处理能力（至少 10 个并发请求），检查响应时间和资源使用

## 9. 文档和部署

- [x] 9.1 编写 API 使用文档（README），包含启动命令、端点说明、示例请求/响应，验证文档准确完整
- [x] 9.2 创建 `api/config.py` 定义配置项（端口、超时、并发限制等），验证配置可通过环境变量覆盖
- [x] 9.3 创建启动脚本 `run_api.sh` 简化本地开发启动，验证脚本正确启动 uvicorn 服务器
- [x] 9.4 验证 API 与现有 CLI 共存不冲突，运行 CLI 和 API 同时工作验证无干扰
