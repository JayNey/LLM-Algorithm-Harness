# [工程质量] REST API 服务封装

## 背景与目标

当前系统仅提供 CLI 接口，难以与其他系统集成。REST API 服务封装可提供标准化的 HTTP 接口，支持其他系统（Web 前端、CI/CD、监控系统）集成，并通过 Webhook 实现异步通知，提升系统的可集成性。

- 分类：工程质量
- 建议优先级：P2（中等价值，与 issue #17 部分重叠）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#17-api-服务封装)

## 背景说明

**注意**：本 issue 与 #17 [功能] 提供本地评测 API 与任务事件接口 有重叠。

- **Issue #17** 专注于 Web/GUI 共用的本地 API（SSE 事件、安全性、单机服务）
- **本 issue** 扩展为更通用的 REST API（包括 Webhook、GraphQL、第三方集成）

建议：
1. 优先实现 #17（核心本地 API）
2. 本 issue 作为 #17 的扩展和增强

## 工作范围

### 1. REST API 端点（与 #17 重叠）
- **任务管理**：
  - `POST /api/v1/evaluate` - 启动评估任务
  - `GET /api/v1/tasks/{task_id}` - 查询任务状态
  - `DELETE /api/v1/tasks/{task_id}` - 取消任务
  - `GET /api/v1/tasks` - 列出所有任务
- **结果查询**：
  - `GET /api/v1/results/{task_id}` - 获取评估结果
  - `GET /api/v1/results/{task_id}/summary` - 获取结果摘要
  - `GET /api/v1/results/{task_id}/export?format=json|csv` - 导出结果
- **题库管理**：
  - `GET /api/v1/problems` - 列出题目库
  - `GET /api/v1/problems/{problem_id}` - 获取题目详情
  - `POST /api/v1/problems/import` - 导入题目
- **配置管理**：
  - `GET /api/v1/models` - 列出可用模型
  - `GET /api/v1/strategies` - 列出可用策略

### 2. Webhook 通知（扩展 #17）
- 配置回调 URL：
  ```json
  {
    "task_id": "task_123",
    "webhook_url": "https://example.com/callback",
    "events": ["task.completed", "task.failed"]
  }
  ```
- 评估完成时自动推送：
  ```json
  POST https://example.com/callback
  {
    "event": "task.completed",
    "task_id": "task_123",
    "status": "completed",
    "result_url": "http://localhost:8080/api/v1/results/task_123"
  }
  ```
- 支持重试和错误处理（3 次重试，指数退避）

### 3. GraphQL 接口（可选扩展）
- 灵活查询语法：
  ```graphql
  query {
    task(id: "task_123") {
      status
      progress
      results {
        problem_id
        passed
        cost
      }
    }
  }
  ```
- 支持复杂过滤和聚合
- 按需返回字段（减少数据传输）

### 4. API 文档和客户端
- OpenAPI (Swagger) 文档自动生成
- 交互式 API 文档（Swagger UI）
- Python SDK：
  ```python
  from harness_client import HarnessClient
  
  client = HarnessClient(base_url="http://localhost:8080")
  task = client.evaluate(config)
  result = client.wait_for_completion(task.id)
  ```

## 验收标准

- [ ] REST API 所有端点正常工作
- [ ] Webhook 通知正确发送并支持重试
- [ ] API 文档自动生成并完整
- [ ] Python SDK 封装完整且易用
- [ ] 单元测试覆盖所有 API 端点
- [ ] 文档更新：API 使用指南和集成示例

## 边界

- 仅提供 REST API，不实现 gRPC 或其他协议
- GraphQL 为可选功能，第一版可不实现
- 不涉及 API 网关、限流、认证（本地单用户服务）

## 依赖与关联

- **前置**：#14 [功能] 可复用评测任务服务（已完成）
- **重叠**：#17 [功能] 提供本地评测 API（核心 API）
- **关联**：#18, #19 Web/GUI 前端（API 消费者）

## 技术要点

### FastAPI 实现
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="LLM Algorithm Harness API")

class EvaluateRequest(BaseModel):
    config: dict
    webhook_url: str = None

@app.post("/api/v1/evaluate")
async def evaluate(request: EvaluateRequest):
    task_id = task_service.create_task(request.config)
    if request.webhook_url:
        register_webhook(task_id, request.webhook_url)
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
```

### Webhook 发送
```python
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=1, min=2, max=10))
def send_webhook(url, payload):
    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
```

### OpenAPI 文档生成
```python
# FastAPI 自动生成
# 访问 http://localhost:8080/docs 查看 Swagger UI
# 访问 http://localhost:8080/openapi.json 获取 OpenAPI 规范
```

## 预期收益

- 实现工作量：约 6-8 天（基于 #17）
- 集成能力：支持多种客户端和系统集成
- 用户价值：CI/CD 集成、监控告警集成
- 生态扩展：社区可开发第三方客户端

## 实施建议

1. **优先级调整**：等 #17 完成后再实施本 issue
2. **合并可能**：考虑将本 issue 合并到 #17，作为其扩展部分
3. **分阶段实施**：
   - Phase 1: 核心 REST API（#17）
   - Phase 2: Webhook 通知（本 issue）
   - Phase 3: GraphQL 和高级功能（可选）
