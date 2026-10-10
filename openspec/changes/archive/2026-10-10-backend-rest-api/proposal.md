## Why

当前项目仅提供 CLI 界面，限制了与第三方系统的集成和 Web 前端开发的进度。通过实现标准化的 REST API，我们可以支持：
1. 异步长时间运行任务的管理和监控
2. Web 前端应用程序的数据驱动交互
3. 第三方服务的集成能力
4. 现有 CLI 能力的程序化访问

## What Changes

- 新增 FastAPI 框架搭建 REST API 服务器
- 创建 v1 API 端点用于评估任务、题目、策略、结果、实验和系统管理
- 实现请求/响应数据模型和统一的响应格式
- 将现有 `src/harness.py` 和 `src/main.py` 的核心逻辑封装为 API 服务
- 配置 CORS、请求验证、错误处理中间件
- 生成 OpenAPI/Swagger 文档供 Web 前端调用

## Capabilities

### New Capabilities

- `api/rest-core`: REST API 核心框架和通用中间件
- `api/evaluation-endpoint`: 评估任务管理（创建、查询、更新、删除）
- `api/problem-endpoint`: 题目管理端点
- `api/strategy-endpoint`: 策略配置端点
- `api/result-endpoint`: 结果查询端点
- `api/experiment-endpoint`: 实验管理端点
- `api/system-endpoint`: 系统状态与健康检查端点
- `api/data-models`: Pydantic 数据模型和请求/响应格式定义
- `api/error-handling`: 统一错误处理和验证

### Modified Capabilities

- `problem-import`: 需要暴露为 API 端点供 Web 前端调用

## Impact

- 新增 `api/` 目录结构
- 新增依赖：FastAPI、uvicorn、pydantic
- CLI 入口 `src/main.py` 保持不变，与新 API 服务共存
- 核心逻辑 `src/harness.py` 保持不变，通过 API 层调用
- 需要配置 CORS 支持跨域请求
- 需要文档生成和 API 验证

