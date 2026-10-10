# LLM Algorithm Harness REST API

## 概述

REST API 为 LLM 算法评估框架提供程序化接口，支持评估任务管理、题目查询、策略配置等功能。

**API 版本**: v1  
**基础 URL**: `http://localhost:8000/api/v1`

## 快速开始

### 1. 启动 API 服务

```bash
./run_api.sh
```

或指定主机和端口：

```bash
./run_api.sh --host 0.0.0.0 --port 8000
```

### 2. 访问文档

- **Swagger UI**: http://localhost:8000/docs
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### 3. 健康检查

```bash
curl http://localhost:8000/api/v1/health
```

响应：

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "0.1.0",
    "service": "LLM Algorithm Harness API"
  },
  "message": "Service is healthy"
}
```

## 统一响应格式

所有 API 响应都遵循统一格式：

### 成功响应

```json
{
  "success": true,
  "data": { /* 端点特定数据 */ },
  "message": "Operation successful"
}
```

### 错误响应

```json
{
  "success": false,
  "error": "error-code",
  "message": "Human-readable error message",
  "details": { /* 可选的详细错误信息 */ }
}
```

## 核心端点

### 评估任务管理

#### 创建评估任务

```
POST /api/v1/evaluations
```

**请求体**:

```json
{
  "problem_ids": ["1", "2", "3"],
  "strategy_names": ["vanilla", "chain_of_thought"],
  "budget_cap_usd": 10.0,
  "timeout_seconds": 300,
  "max_concurrency": 5
}
```

**响应** (201 Created):

```json
{
  "success": true,
  "data": {
    "evaluation_id": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2024-10-10T15:30:45Z",
    "updated_at": "2024-10-10T15:30:45Z",
    "status": "pending",
    "strategy_names": ["vanilla", "chain_of_thought"],
    "problem_count": 3,
    "spent_usd": 0.0,
    "budget_cap_usd": 10.0,
    "progress": {
      "completed": 0,
      "total": 3,
      "percentage": 0.0
    }
  },
  "message": "Evaluation created successfully"
}
```

#### 列出评估任务

```
GET /api/v1/evaluations?status=running&limit=20&offset=0
```

**查询参数**:

- `status` (optional): 按状态过滤 - `pending`, `running`, `completed`, `failed`, `cancelled`
- `limit` (optional): 每页数量，默认 20，最大 100
- `offset` (optional): 偏移数量，默认 0

**响应** (200 OK):

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "evaluation_id": "550e8400-e29b-41d4-a716-446655440000",
        "created_at": "2024-10-10T15:30:45Z",
        "updated_at": "2024-10-10T15:30:45Z",
        "status": "running",
        "strategy_names": ["vanilla"],
        "problem_count": 3,
        "spent_usd": 2.5,
        "budget_cap_usd": 10.0,
        "progress": {
          "completed": 2,
          "total": 3,
          "percentage": 66.67
        }
      }
    ],
    "total": 1,
    "limit": 20,
    "offset": 0,
    "has_more": false
  },
  "message": "Evaluations retrieved successfully"
}
```

#### 获取单个评估任务

```
GET /api/v1/evaluations/{evaluation_id}
```

**响应** (200 OK): 返回评估任务详情（见上方示例）

**错误** (404 Not Found): 任务不存在

#### 更新评估任务配置

```
PATCH /api/v1/evaluations/{evaluation_id}
```

**请求体** (全部可选):

```json
{
  "budget_cap_usd": 15.0,
  "timeout_seconds": 600
}
```

**限制**: 仅 `pending` 状态的任务可修改

**响应** (200 OK): 返回更新后的任务信息

**错误**:
- 404 Not Found: 任务不存在
- 400 Bad Request: 任务状态不允许修改

#### 删除评估任务

```
DELETE /api/v1/evaluations/{evaluation_id}
```

**限制**: 仅 `pending` 或 `completed` 状态的任务可删除

**响应** (204 No Content): 删除成功

**错误**:
- 404 Not Found: 任务不存在
- 400 Bad Request: 任务状态不允许删除

#### 启动评估任务

```
POST /api/v1/evaluations/{evaluation_id}/start
```

**响应** (202 Accepted): 任务已启动，在后台执行

```json
{
  "success": true,
  "data": {
    "evaluation_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "running",
    ...
  },
  "message": "Evaluation started successfully"
}
```

**错误**:
- 404 Not Found: 任务不存在
- 400 Bad Request: 任务已在运行或已完成

#### 获取任务执行进度

```
GET /api/v1/evaluations/{evaluation_id}/progress
```

**响应** (200 OK):

```json
{
  "success": true,
  "data": {
    "completed": 2,
    "total": 3,
    "percentage": 66.67
  },
  "message": "Progress retrieved successfully"
}
```

#### 取消评估任务

```
POST /api/v1/evaluations/{evaluation_id}/cancel
```

**限制**: 仅 `running` 状态的任务可取消

**响应** (200 OK): 返回更新后的任务信息（status 为 `cancelled`）

**错误**:
- 404 Not Found: 任务不存在
- 400 Bad Request: 任务状态不允许取消

## 错误处理

API 使用标准 HTTP 状态码：

| 状态码 | 含义 | 示例 |
|--------|------|------|
| 200 | OK | 请求成功 |
| 201 | Created | 资源创建成功 |
| 202 | Accepted | 异步请求已接受 |
| 204 | No Content | 删除成功 |
| 400 | Bad Request | 参数验证失败、状态冲突 |
| 404 | Not Found | 资源不存在 |
| 500 | Internal Server Error | 服务器错误 |

## 配置

通过环境变量配置 API：

```bash
export API_HOST=0.0.0.0
export API_PORT=8000
export MAX_CONCURRENT_TASKS=5
export TASK_TIMEOUT_SECONDS=3600
```

或在 `.env` 文件中设置。

## 使用示例

### Python

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# 创建评估任务
response = requests.post(
    f"{BASE_URL}/evaluations",
    json={
        "problem_ids": ["1", "2", "3"],
        "strategy_names": ["vanilla"],
        "budget_cap_usd": 10.0,
    }
)
evaluation = response.json()["data"]
eval_id = evaluation["evaluation_id"]

# 启动任务
response = requests.post(f"{BASE_URL}/evaluations/{eval_id}/start")
assert response.status_code == 202

# 轮询进度
import time
while True:
    response = requests.get(f"{BASE_URL}/evaluations/{eval_id}/progress")
    progress = response.json()["data"]
    print(f"Progress: {progress['completed']}/{progress['total']}")
    
    if progress["completed"] == progress["total"]:
        break
    time.sleep(1)
```

### cURL

```bash
# 创建评估任务
curl -X POST http://localhost:8000/api/v1/evaluations \
  -H "Content-Type: application/json" \
  -d '{
    "problem_ids": ["1", "2", "3"],
    "strategy_names": ["vanilla"],
    "budget_cap_usd": 10.0
  }'

# 启动任务 (replace with actual ID)
curl -X POST http://localhost:8000/api/v1/evaluations/{eval_id}/start

# 获取进度
curl http://localhost:8000/api/v1/evaluations/{eval_id}/progress
```

## 限制和注意事项

1. **并发限制**: 默认最多 5 个并发任务，超出时排队等待
2. **状态内存存储**: 第 1 阶段使用内存存储，服务重启时数据丢失。后续版本将支持数据库存储
3. **WebSocket 支持**: 当前不支持 WebSocket 实时推送，请使用轮询。后续版本计划支持
4. **认证**: 第 1 阶段不包含认证机制，部署时建议在反向代理层添加

## 路线图

- Phase 2: 数据库持久化存储
- Phase 3: WebSocket 实时推送
- Phase 4: 用户认证和授权
- Phase 5: 完整的问题和策略端点

## 反馈和支持

如有问题或建议，请联系开发团队或提交 Issue。
