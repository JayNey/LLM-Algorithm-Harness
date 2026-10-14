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
    "scope": "api_liveness_only",
    "version": "0.1.0",
    "service": "LLM Algorithm Harness API"
  },
  "message": "Service is healthy"
}
```

该公开端点只检查 API 存活。数据库、Docker 和系统资源需使用受管理员保护的监控端点，详见 [监控指南](docs/api-monitoring.md)。

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

**请求体** (`model` 为必填字段，缺失返回 400):

```json
{
  "api_key_id": "your-stored-key-id",
  "model": "gpt-4o-mini",
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
    "model": "gpt-4o-mini",
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
        "model": "gpt-4o-mini",
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

**进度分母口径**：`progress.total` 仍为**题目数**（`problem_count`），而 `current`/`completed` 是**单元数**（题目数 × 策略数）；`percentage` 以单元总数为分母计算，并恒落在 [0, 100]。两者分母不同，因此多策略评估时 `current/total` 的比值不等于 `percentage`（2 策略 × 2 题目全完成时 `percentage=100`，而 `current=4`、`total=2`）。评估详情响应若带异步任务上报的 `progress`，其 `current`/`total` 均为单元数。

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
        "model": "gpt-4o-mini",
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
    "model": "gpt-4o-mini",
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
2. **任务持久化**: #151 已将任务状态存入业务数据库，#179 已提供 Celery/Redis 与 AsyncTask 基础，#180 已增加实验、导入和基准 Celery 入口。现有 HTTP 路由没有因此自动切换队列。重启后记录仍可查询；旧评估启动恢复规则不代表异步队列恢复执行保障。当前 `/evaluations` 路由仍保留旧流程。异步评估 worker 现已改为经真实 `AlgorithmHarness` 执行（LLM 调用 + Docker 沙箱运行 + 成本统计），逐单元结果落库，不再返回模拟结果。
3. **WebSocket 支持**: 当前不支持 WebSocket 实时推送，请使用轮询。后续版本计划支持
4. **认证**: 用户、Token 撤销和加密密钥已实现；详见 [认证指南](docs/api-authentication.md)。队列基础与三类 Celery 任务（实验、导入、基准）实现已合并，但其端到端执行和真实 LLM 指标仍未接通或验证。异步评估 worker 现已改为经真实 `AlgorithmHarness` 执行（见第 2 条）；真实 LLM 调用的端到端执行与使用计量仍待生产环境验证（测试不发起在线调用），密钥使用计量和安全结果发布仍需接入，#149 保持开放。

## 路线图

- 数据库持久化存储：#151 已实现
- Phase 3: WebSocket 实时推送
- 用户认证和授权：#152 已实现
- 系统监控：#157 已提供健康、资源、日志、API 与业务 SQL 查询统计，并分别只读查询旧评估和异步任务；队列/worker 连通探测与真实 LLM 指标尚待接入
- Phase 5: 完整的问题和策略端点

## 反馈和支持

如有问题或建议，请联系开发团队或提交 Issue。

## 文件上传与下载

支持私有题库/配置上传、JSON/CSV 批量导入、进度查询和结果多格式下载。接口、上传限制及 worker 接入见 [文件服务指南](docs/api-files.md)。所有接口复用 Bearer 认证和资源所有者校验。

## 系统监控与安全日志

本次 #157 基础能力提供 `/system/health`、`/health/database`、`/health/sandbox`、`/system/resources`、`/metrics/api-stats`、业务 SQL 查询统计和离线配置目录。系统级端点及全局 `/logs` 需要有效 Bearer 身份，并由部署者通过 `MONITOR_ADMIN_USER_IDS` UUID 白名单授权。

用户可读取自己的 `/logs/tasks/{task_id}`、下载 `/logs/download/{task_id}`，以及查询 `/quotas/usage` 的既有存储、请求与导入限额。任务日志按所有者隔离，消息和上下文在存储前脱敏；不接受主机日志路径。

`/health/database` 只读检查已配置的认证/文件 SQLite 和 #151 业务 engine 的连通性、所需表与迁移版本；不通过健康请求迁移数据库或重新创建任务服务。`/system/tasks/running` 与 `/system/tasks/queued` 支持 `task_source=legacy_evaluation`（默认）或 `async_task`，分别读取未关联异步任务的 Evaluation 或 AsyncTask，支持 `limit/offset` 分页并返回准确 `total/counts`。关联评估不再计入旧来源，避免双计；`queued` 表示数据库 `pending` 状态，不代表 Redis 队列长度。`/system/status` 分别提供两组全量状态计数，不能相加视作全局一致快照。监控不轮询 Celery 或提交任务状态，也不暴露原始参数、进度消息、错误详情及 Celery 任务 ID。

API 与业务 SQL 指标提供 `window_complete` 与 `retained_sample`，窗口不完整时顶层累计值为 `null`。业务 SQL 统计仅覆盖当前评估 engine 与 API 进程的 cursor 执行阶段，未纳入异步任务独立 engine 的全部查询；重启后重建采集起点，不保存 SQL、参数或连接凭据。#179 的队列基础与 #180 的实验/导入/基准入口已存在，Redis/worker 本轮未联网探测，标记 `not_checked`；`evaluation_worker_implementation=mock` 只指评估 worker，真实评估与 LLM 延迟/成功率标记 `not_configured/null`。管理员配置、全部接口和后续接入边界见 [监控指南](docs/api-monitoring.md)，#157 保持开放。
