# Async Task Queue API

## Purpose

提供异步任务队列系统，支持长时间运行的评估任务在后台执行，避免 HTTP 请求超时。用户通过 API 创建任务、查询状态、暂停/恢复/取消任务。

---

## Requirements

### REQ-ATQ-001: 异步任务创建

POST /evaluations SHALL 立即返回（< 1 秒），任务状态为 `pending`；后台 Celery worker SHALL 异步执行任务，无需保持 HTTP 连接。

**验收场景 1**：大任务立即返回
```
GIVEN 用户提交包含 100 个 problem 的 evaluation 请求
WHEN API 处理 POST /evaluations
THEN 在 500ms 内返回响应
AND 响应中 status = "pending"
AND 响应中包含 evaluation_id
AND HTTP 连接立即关闭
```

**验收场景 2**：任务异步执行
```
GIVEN 评估任务已创建（status="pending"）
WHEN HTTP 客户端关闭连接
THEN 后台 Celery worker 继续执行任务
AND 5 秒后查询状态，status 变为 "running"
```

**验收场景 3**：并发创建
```
GIVEN 用户同时提交 10 个 evaluation 请求
WHEN API 处理这些请求
THEN 所有请求在 1 秒内返回
AND 每个请求返回唯一的 evaluation_id
AND 所有任务进入 Celery 队列
```

---

### REQ-ATQ-002: 实时状态查询

GET /evaluations/{id} SHALL 聚合 Celery 实时状态和数据库记录，返回最新的任务状态和进度（current/total/message）。

**验收场景 1**：运行中任务的实时进度
```
GIVEN 任务正在执行（status="running"）
AND 已完成 10/100 个单元
WHEN 调用 GET /evaluations/{id}
THEN 返回 status = "running"
AND progress.current = 10
AND progress.total = 100
AND progress.message 包含 "Completed 10/100"
```

**验收场景 2**：查询响应时间
```
GIVEN 任务存在于数据库
WHEN 调用 GET /evaluations/{id}
THEN 响应时间 < 200ms
AND 包含最新的 Celery 状态（如果任务运行中）
```

**验收场景 3**：终止状态的查询
```
GIVEN 任务已完成（status="completed"）
WHEN 调用 GET /evaluations/{id}
THEN 返回 status = "completed"
AND completed_count 显示完成的单元数
AND failed_count 显示失败的单元数
AND completed_at 显示完成时间
```

---

### REQ-ATQ-003: 任务暂停（优雅停止）

POST /evaluations/{id}/pause SHALL 请求暂停任务；Celery worker SHALL 在当前单元完成后停止，未执行的单元保持 `queued` 状态。

**验收场景 1**：优雅停止机制
```
GIVEN 任务正在执行第 10/100 个单元
WHEN 用户调用 POST /evaluations/{id}/pause
THEN API 立即返回 200（暂停请求已接受）
AND 当前单元（第 10 个）继续执行完成
AND 任务在单元边界停止（通常 < 60 秒）
AND 最终 status = "paused"
AND completed_count = 10
```

**验收场景 2**：暂停后的状态
```
GIVEN 任务已暂停（status="paused"）
WHEN 查询任务状态
THEN status = "paused"
AND completed_count 记录已完成的单元数
AND 未执行的单元状态为 "queued"
AND 正在执行的单元标记为 "uncertain"
```

**验收场景 3**：预算限制自动暂停
```
GIVEN 任务设置了 budget_cap_usd = 5.0
AND 已花费 4.9 USD
WHEN 下一个单元执行后总花费达到 5.1 USD
THEN 任务自动暂停（status="paused"）
AND error_message = "Budget cap reached"
```

**验收场景 4**：暂停非运行状态的任务
```
GIVEN 任务状态为 "pending" 或 "completed"
WHEN 调用 POST /evaluations/{id}/pause
THEN 返回 400 错误
AND 错误信息 "Cannot pause task in status 'pending'"
```

---

### REQ-ATQ-004: 任务恢复

POST /evaluations/{id}/resume SHALL 恢复暂停或失败的任务；Celery worker SHALL 跳过已完成的单元，继续执行 `queued` 状态的单元。

**验收场景 1**：恢复暂停的任务
```
GIVEN 任务已暂停（status="paused", completed_count=10, total=100）
WHEN 调用 POST /evaluations/{id}/resume
THEN 创建新的 Celery 任务
AND 任务从第 11 个单元继续执行
AND 已完成的 10 个单元不会重复执行
AND status 变为 "pending" 然后 "running"
```

**验收场景 2**：恢复失败的任务
```
GIVEN 任务失败（status="failed", completed_count=50, total=100）
WHEN 调用 POST /evaluations/{id}/resume
THEN 标记为 "uncertain" 的单元重新执行
AND 已完成的 50 个单元不会重复执行
AND 继续执行剩余的 50 个单元
```

**验收场景 3**：恢复非终止状态的任务
```
GIVEN 任务正在运行（status="running"）
WHEN 调用 POST /evaluations/{id}/resume
THEN 返回 400 错误
AND 错误信息 "Cannot resume task in status 'running'"
```

---

### REQ-ATQ-005: 任务取消

DELETE /evaluations/{id} SHALL 取消任务并删除所有记录（evaluation + async_task + TaskService JSON）；任务不可恢复。

**验收场景 1**：取消运行中的任务
```
GIVEN 任务正在执行（status="running"）
WHEN 调用 DELETE /evaluations/{id}
THEN Celery 任务被 revoke（terminate=False）
AND 当前单元执行完成后退出
AND 任务状态变为 "cancelled"
AND evaluation 记录被删除
AND async_task 记录被删除
AND TaskService JSON 文件被删除
```

**验收场景 2**：删除后查询
```
GIVEN evaluation 已被删除
WHEN 调用 GET /evaluations/{id}
THEN 返回 404 错误
AND 错误信息 "Evaluation '{id}' not found"
```

**验收场景 3**：删除完成的任务
```
GIVEN 任务已完成（status="completed"）
WHEN 调用 DELETE /evaluations/{id}
THEN evaluation 记录被删除
AND async_task 记录被删除
AND TaskService JSON 文件被删除
AND Celery 任务不需要 revoke（已终止）
```

---

### REQ-ATQ-006: 错误处理和重试

Celery 任务 SHALL 区分业务错误（不重试）和基础设施错误（自动重试最多 3 次）；业务错误 SHALL 立即标记任务为 `failed` 并记录错误信息。

**验收场景 1**：业务错误不重试
```
GIVEN API key 无效
WHEN Celery worker 开始执行任务
THEN 任务立即失败（status="failed"）
AND error_message = "Invalid API key"
AND 不触发重试
AND 失败时间 < 5 秒
```

**验收场景 2**：基础设施错误自动重试
```
GIVEN Redis 连接超时（瞬时故障）
WHEN Celery worker 第 1 次执行失败
THEN 10 秒后自动重试（第 2 次）
AND 如果第 2 次失败，20 秒后重试（第 3 次）
AND 如果第 3 次失败，40 秒后重试（第 4 次）
AND 如果第 4 次仍失败，标记为 "failed"
```

**验收场景 3**：单元级错误不影响整体任务
```
GIVEN 任务包含 10 个单元
AND 第 3 个单元的 LLM API 调用失败
WHEN 任务执行
THEN 第 3 个单元标记为 "failed"
AND 其他 9 个单元继续执行
AND 整体任务 status = "completed"
AND failed_count = 1
AND completed_count = 9
```

**验收场景 4**：配置错误不重试
```
GIVEN strategy 名称不存在
WHEN Celery worker 验证配置
THEN 任务立即失败（status="failed"）
AND error_message = "Strategy 'xxx' not found"
AND 不触发重试
```

---

### REQ-ATQ-007: 任务历史清理

Celery 结果 SHALL 在 7 天后自动过期；DELETE /evaluations/{id} SHALL 同步删除 async_task 记录和 TaskService JSON 文件。

**验收场景 1**：Celery 结果自动过期
```
GIVEN 任务完成 7 天前（created_at = now() - 7 days）
WHEN 任务完成后经过 7 天
THEN Redis 中的 Celery 结果自动删除
AND 数据库中的 async_task 和 evaluation 记录保留
AND 查询任务状态仍能返回数据库记录
```

**验收场景 2**：删除时同步清理
```
GIVEN evaluation 存在 async_task 和 TaskService JSON 文件
WHEN 调用 DELETE /evaluations/{id}
THEN evaluation 记录被删除
AND async_task 记录被删除
AND TaskService JSON 文件（/data/tasks/{run_id}.json）被删除
AND 所有关联资源清理完成
```

**验收场景 3**：数据库记录可永久保留
```
GIVEN 任务完成 30 天前
WHEN 配置 AUTO_CLEANUP_ENABLED = false（默认）
THEN evaluation 和 async_task 记录仍存在于数据库
AND 可以查询历史任务
```

**验收场景 4**：可选的自动清理
```
GIVEN 配置 AUTO_CLEANUP_ENABLED = true, AUTO_CLEANUP_DAYS = 30
AND 任务完成 30 天前
WHEN 定时清理任务运行
THEN 完成/失败/取消的任务自动删除
AND 运行中/暂停的任务不被删除
```
