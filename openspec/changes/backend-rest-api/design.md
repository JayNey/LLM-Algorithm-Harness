## Context

现有项目仅提供 CLI 接口（通过 argparse），核心逻辑分散在 `src/harness.py`（协调主流程）、`src/models.py`（数据模型）和 `src/task_service.py`（任务管理）中。CLI 支持完整的评估工作流，包括任务创建、执行、成本追踪和报告生成。

为支持 Web 前端，需要将这些核心能力通过 REST API 暴露。现有的数据模型（Pydantic-based）和业务逻辑可被 API 层直接复用。

## Goals / Non-Goals

**Goals:**
- 将现有 CLI 能力转换为可编程的 REST API
- 支持异步任务管理和实时进度监控
- 为 Web 前端提供完整的数据驱动接口
- 保持 API 与现有 CLI 行为一致
- 提供自动 OpenAPI/Swagger 文档

**Non-Goals:**
- 修改现有 CLI 实现或 `src/harness.py` 核心逻辑
- 实现用户认证和授权系统（阶段 1 为内部使用）
- 提供生产级的任务持久化存储（后续迭代）
- 支持 WebSocket 实时更新（后续迭代）

## Decisions

### 1. 框架选择：FastAPI

**决策**：使用 FastAPI 而非 Flask。

**理由**：
- 自动 OpenAPI/Swagger 生成（零配置）
- 内置 Pydantic 集成，复用现有数据模型无缝
- 异步支持（async/await），便于后续实现后台任务
- 性能优于 Flask（基于 Starlette 和 uvicorn）
- 更丰富的错误处理和验证机制

**替代方案**：
- Flask：更轻量但文档和验证需手写，不如 FastAPI 优雅
- Django：过度设计，项目规模不需要 ORM 和 admin panel

### 2. 项目结构：API 层隔离

**决议**：创建 `api/` 目录，包含路由、中间件和 API 数据模型，保持与 `src/` 核心逻辑的分离。

```
api/
  __init__.py
  main.py              # FastAPI 应用入口
  middleware/          # 中间件（CORS、日志、错误处理）
  routes/              # 路由模块
    evaluations.py
    problems.py
    strategies.py
    results.py
    experiments.py
    system.py
  models.py            # API 特定的请求/响应模型（Pydantic）
  schemas.py           # API 共享的数据结构定义
  services/            # 业务逻辑适配层（连接 API 和 src/harness）
    evaluation_service.py
    task_service_adapter.py
```

**理由**：
- API 层隐藏 CLI 逻辑，不污染核心 `src/` 模块
- 前后端路由清晰，便于维护和扩展
- 支持未来的多前端场景（CLI 和 API 共存）

### 3. 数据模型映射：零转换原则

**决议**：API 响应直接使用 `src/models.py` 中的现有 Pydantic 模型，避免重复定义。

**理由**：
- `Problem`、`ExecutionResult`、`HarnessConfig` 等已是 Pydantic BaseModel
- FastAPI 自动支持 Pydantic 模型序列化为 JSON
- 减少数据转换开销

**例外**：
- API 特定的包装模型（如 `EvaluationCreateRequest`）在 `api/models.py` 中定义
- 统一的 `ApiResponse<T>` 响应包装器

### 4. 任务执行：异步运行，状态追踪

**决议**：API `/evaluations/{id}/start` 端点立即返回 202 Accepted，任务在后台线程或后台进程中运行。

**实现**：
- 使用 Python `threading.Thread` 或 `multiprocessing` 进行后台执行（第 1 阶段）
- 在内存中维护任务状态字典，对应 `taskId → ExecutionState`
- 提供 `/evaluations/{id}/progress` 端点实时查询进度

**理由**：
- 避免 HTTP 超时（评估任务可能耗时数分钟/小时）
- 支持 Web 前端的异步轮询
- 后续可升级为消息队列（Celery + Redis）

**权衡**：
- 内存中的状态在服务重启后丢失（后续通过数据库改进）
- 不支持分布式任务执行（后续迭代）

### 5. 错误处理：统一 API 异常类

**决议**：定义 `ApiError` 基类和特定子类（`ValidationError`、`NotFoundError` 等），全局异常处理器将其转换为统一的 JSON 响应。

**理由**：
- 一致的错误格式使客户端更容易处理
- 减少每个端点中的重复错误处理代码
- 易于添加监控和日志

### 6. 中间件栈

**顺序**：
1. CORS 中间件 - 允许浏览器跨域请求
2. 日志中间件 - 记录请求/响应
3. 错误处理 - 全局异常捕获

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| 内存中状态丢失 | 服务启动时支持状态恢复（第 2 阶段）；文档明确说明限制 |
| 并发任务数无限制 | 第 1 阶段限制最多 N 个并发任务（通过信号量）；后续迁移到任务队列 |
| 长期运行任务无监督 | `/progress` 端点可监控；超时配置可防止僵尸任务 |
| 初版不支持 WebSocket | 文档标记为"后续迭代"；轮询足以满足早期 Web 前端需求 |
| 缺少认证 | 部署时在反向代理层添加认证；本阶段 API 仅供内部使用 |

## Migration Plan

### 第 1 阶段（本次 change）
1. 搭建 FastAPI 基础框架，实现 `/api/v1/health` 验证
2. 创建第一个完整的评估端点 (CRUD + start + progress)
3. 验证与现有 CLI 逻辑的集成

### 第 2 阶段（后续 PR）
1. 添加其他端点（问题、策略、实验等）
2. 集成数据库存储任务状态
3. 迁移到后台任务队列（Celery）

## Open Questions

1. 是否需要在第 1 阶段实现所有端点，还是只关注评估端点？
   - **答**：优先完成评估端点的完整 CRUD 和执行流程，其他端点在第 2 阶段补充

2. 异步任务的超时设置是多少？
   - **答**：使用配置文件设定（默认 1 小时），后续迭代支持按任务定制

3. 并发执行任务的数量限制？
   - **答**：第 1 阶段硬限制为 5 个并发任务，防止资源耗尽
