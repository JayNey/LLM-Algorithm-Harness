# LLM Algorithm Harness REST API

## 概述

REST API 为 LLM 算法评估框架提供程序化接口，支持评估任务管理、题目查询、策略配置等功能。

**API 版本**: v1  
**基础 URL**: `http://localhost:8000/api/v1`

## 快速开始

### 1. 配置认证并启动 API 服务

先按 [认证指南](docs/api-authentication.md) 设置 `SECRET_KEY` 和 `ENCRYPTION_KEY`；无有效密钥时服务拒绝启动。注册、登录、保存 LLM API 密钥后，全部评估请求必须带 `Authorization: Bearer <access_token>`。创建任务还需提供自己的 `api_key_id`。

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

成功响应使用下列包装。参数校验和内部错误使用结构化错误；认证、权限和状态错误使用 FastAPI 的 `detail` 格式：

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
  "api_key_id": "your-stored-key-id",
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
    "error_message": null,
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

### 实验与基准管理（#156）

实验、基准 Suite、A/B 测试均 owner 作用域；请求永不携带明文密钥，`api_key_id` 在创建时校验归属、运行时经认证库解密注入；`dataset_path` 只允许 `DATA_ROOT`（默认 `data/`）内的路径。

| 端点 | 说明 |
|---|---|
| `POST /api/v1/experiments` | 创建固定预算实验（校验密钥归属与数据集路径） |
| `GET /api/v1/experiments` | 实验列表（`status`/`limit`/`offset`） |
| `GET /api/v1/experiments/{id}` | 实验详情 |
| `DELETE /api/v1/experiments/{id}` | 删除（运行中拒绝） |
| `POST /api/v1/experiments/{id}/run` | 异步运行（`ExperimentRunner`） |
| `GET /api/v1/experiments/{id}/results` | 结果摘要（需 completed） |
| `GET /api/v1/experiments/{id}/comparison` | 模型×策略对比报告（含胜率矩阵/McNemar） |
| `GET /api/v1/experiments/{id}/panel` | 交互面板数据 |
| `POST /api/v1/pareto/analyze` | 成本-准确率帕累托分析（无状态，输入 comparisons） |
| `POST /api/v1/optimize` | 成本优化建议（无状态，含性价比排名与预算方案） |
| `GET /api/v1/benchmarks/suites` | Suite 列表 |
| `POST /api/v1/benchmarks/suites` | 创建 Suite（默认 `frozen: false`） |
| `GET /api/v1/benchmarks/suites/{id}` | Suite 详情 |
| `PATCH /api/v1/benchmarks/suites/{id}` | 更新 Suite（frozen 拒绝，返回 400） |
| `POST /api/v1/benchmarks/suites/{id}/run` | 异步运行基准（`BenchmarkExecutor`） |
| `GET /api/v1/benchmarks/runs/{run_id}` | 运行结果（含 accuracy/cost 与原始 results） |
| `GET /api/v1/benchmarks/learning-curve/{suite_id}` | 学习曲线（时间序列 + 趋势；空历史返回空序列） |
| `POST /api/v1/ab-tests` | 创建 A/B 测试 |
| `GET /api/v1/ab-tests` | A/B 列表 |
| `GET /api/v1/ab-tests/{id}` | A/B 详情 |
| `DELETE /api/v1/ab-tests/{id}` | 删除（运行中拒绝） |
| `POST /api/v1/ab-tests/{id}/run` | 异步运行（`ABTestRunner`） |
| `GET /api/v1/ab-tests/{id}/results` | A/B 结果（含显著性检验，来自产物 `ab_test.json`） |

异步端点返回 `202`，随后通过详情端点轮询状态（`pending → running → completed/failed`）；服务重启会把中断的 `pending/running` 任务标记为 `failed`（`error_message: "interrupted by service restart"`）。

### 成本追踪、预算与定价（#154）

成本查询为只读聚合（数据来自评估任务与基准运行的持久化记录）；预算/预警/定价覆盖为 owner 作用域的配置持久化。时间段参数（`since`/`until`）接受 ISO 8601，非法值返回 400。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/costs/tasks/{task_id}` | 单任务成本（跨评估/实验/基准/A-B 四类任务解析） |
| `GET /api/v1/costs/summary` | 用户成本汇总（`since`/`until`，按来源类型分列） |
| `GET /api/v1/costs/trends` | 按日成本趋势序列 |
| `GET /api/v1/costs/breakdown` | 成本分解（按来源/模型/策略） |
| `GET /api/v1/budgets` · `POST /api/v1/budgets` | 读取 / 首次设置预算（全局上限 + 按难度分配 + `action: pause\|downgrade`） |
| `PATCH /api/v1/budgets` | 部分更新预算（未传字段保持不变） |
| `GET /api/v1/budgets/usage` | 使用情况：全局 used/remaining/percentage + 按难度（难度用量为比例估计，响应 `basis` 注明口径） |
| `GET /api/v1/alerts` · `POST /api/v1/alerts` | 预警规则列表 / 创建（threshold_pct 1–100；channel: slack/webhook/smtp/log；webhook、smtp 必须带 target） |
| `PATCH /api/v1/alerts/{id}` · `DELETE /api/v1/alerts/{id}` | 更新 / 删除规则 |
| `GET /api/v1/alerts/history` | 触发历史（运行期触发接线随 #149 队列落地） |
| `GET /api/v1/pricing` | 定价目录（内置 + pricing.json + 数据库覆盖，覆盖优先） |
| `GET /api/v1/pricing/{model_id}/history` | 自定义定价版本历史（追加式，最新在前） |
| `POST /api/v1/pricing/{model_id}` | 自定义定价覆盖（USD/1k tokens，仅 API 成本查询侧生效；runner 接线随 #159） |
| `GET /api/v1/reports/cost/{task_id}` | 任务成本报告（含 percentage_used 与定价元数据） |
| `GET /api/v1/reports/cost-optimization` | 从用户自己的 run 数据合成对比并生成优化建议（build_advisory） |

预警规则的 webhook/邮件目标在响应中脱敏（保留协议与主机）。删除规则用 `DELETE`，成功返回 204。

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
export DATABASE_URL=sqlite:///data/business/business.sqlite3
```

`DATABASE_URL` 指向业务数据库（评估任务、结果与题库）。默认使用本地 SQLite 文件
`data/business/business.sqlite3`，schema 由 Alembic 迁移在启动时自动升级；生产环境可
切换为 PostgreSQL 连接串（如 `postgresql+psycopg://user:pass@host/business`）。认证
数据独立存储在 `AUTH_DATABASE_PATH`，与业务库物理隔离。

或在 `.env` 文件中设置。

## 使用示例

### Python

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# 先登录，再使用返回的访问 Token 和自己保存的密钥 ID
ACCESS_TOKEN = "your-access-token"
API_KEY_ID = "your-stored-key-id"
session = requests.Session()
session.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"

# 创建评估任务
response = session.post(
    f"{BASE_URL}/evaluations",
    json={
        "api_key_id": API_KEY_ID,
        "problem_ids": ["1", "2", "3"],
        "strategy_names": ["vanilla"],
        "budget_cap_usd": 10.0,
    }
)
evaluation = response.json()["data"]
eval_id = evaluation["evaluation_id"]

# 启动任务
response = session.post(f"{BASE_URL}/evaluations/{eval_id}/start")
assert response.status_code == 202

# 轮询进度
import time
while True:
    response = session.get(f"{BASE_URL}/evaluations/{eval_id}/progress")
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
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "api_key_id": "your-stored-key-id",
    "problem_ids": ["1", "2", "3"],
    "strategy_names": ["vanilla"],
    "budget_cap_usd": 10.0
  }'

# 启动任务 (replace with actual ID)
curl -X POST http://localhost:8000/api/v1/evaluations/{eval_id}/start -H "Authorization: Bearer $ACCESS_TOKEN"

# 获取进度
curl http://localhost:8000/api/v1/evaluations/{eval_id}/progress -H "Authorization: Bearer $ACCESS_TOKEN"
```

## 限制和注意事项

1. **并发限制**: 默认最多 5 个并发任务，超出时排队等待
2. **状态内存存储**: 第 1 阶段使用内存存储，服务重启时数据丢失。后续版本将支持数据库存储
3. **WebSocket 支持**: 当前不支持 WebSocket 实时推送，请使用轮询。后续版本计划支持
4. **认证**: 用户、Token 撤销和加密密钥已实现；详见 [认证指南](docs/api-authentication.md)。业务任务仍使用模拟执行器，真实执行由 #149 接入。

## 路线图

- Phase 2: 数据库持久化存储
- Phase 3: WebSocket 实时推送
- 用户认证和授权：#152 已实现，等待审查合并
- Phase 5: 完整的问题和策略端点

## 反馈和支持

如有问题或建议，请联系开发团队或提交 Issue。

## 文件上传与下载

支持私有题库/配置上传、JSON/CSV 批量导入、进度查询和结果多格式下载。接口、上传限制及 worker 接入见 [文件服务指南](docs/api-files.md)。所有接口复用 Bearer 认证和资源所有者校验。
