# Database Schema Delta Spec

## MODIFIED Requirements

### REQ-DB-004: 异步任务状态持久化

系统 SHALL 新增 `async_tasks` 表存储异步任务元数据（task_type、entity_id、status、progress、celery_task_id）；任务状态更新 SHALL 实时同步到该表，服务重启后任务状态 SHALL 保持可查询。

**验收场景 1**：创建 evaluation 时自动创建 async_task
```
GIVEN 用户提交 POST /evaluations 请求
WHEN API 创建 Evaluation 记录
THEN 自动创建对应的 AsyncTask 记录
AND AsyncTask.task_type = "evaluation"
AND AsyncTask.entity_id = Evaluation.id
AND AsyncTask.status = "pending"
AND AsyncTask.celery_task_id 不为空
```

**验收场景 2**：任务执行时状态实时更新
```
GIVEN Celery worker 开始执行任务
WHEN 任务状态从 pending 变为 running
THEN AsyncTask.status 更新为 "running"
AND AsyncTask.started_at 记录开始时间
AND AsyncTask.progress 包含 {"current": 0, "total": N}
```

**验收场景 3**：服务重启后状态可查询
```
GIVEN 任务正在运行中（status="running"）
WHEN API 服务重启
AND 用户调用 GET /evaluations/{id}
THEN 返回正确的任务状态和进度
AND 状态从数据库 async_tasks 表恢复
```

**验收场景 4**：任务完成后状态持久化
```
GIVEN 任务执行完成
WHEN Celery worker 更新最终状态
THEN AsyncTask.status = "completed" 或 "failed"
AND AsyncTask.completed_at 记录完成时间
AND 错误信息（如有）记录到 AsyncTask.error_message
```

---

### REQ-DB-005: Evaluation 表关联异步任务

`evaluations` 表 SHALL 增加 `async_task_id` 外键字段关联 `async_tasks.id`；查询 evaluation 时 SHALL 能聚合异步任务的实时状态和进度。

**验收场景 1**：外键关联正确建立
```
GIVEN 创建 Evaluation 和 AsyncTask
WHEN Evaluation.async_task_id 设置为 AsyncTask.id
THEN 数据库外键约束验证通过
AND 删除 AsyncTask 时 Evaluation.async_task_id 置为 NULL（ON DELETE SET NULL）
```

**验收场景 2**：查询时聚合实时状态
```
GIVEN Evaluation 关联了 AsyncTask
WHEN 调用 GET /evaluations/{id}
THEN 响应中的 status 优先使用 AsyncTask.status（更实时）
AND 响应中的 progress 来自 AsyncTask.progress
AND Evaluation 表的 status 作为备用（兼容性）
```

**验收场景 3**：AsyncTask 不存在时的兼容性
```
GIVEN Evaluation.async_task_id 为 NULL（旧数据或手动删除）
WHEN 调用 GET /evaluations/{id}
THEN 使用 Evaluation 表的 status 字段
AND progress 为 NULL
AND 不报错，正常返回
```

**验收场景 4**：批量查询时的性能
```
GIVEN 用户有 100 个 Evaluation 记录
WHEN 调用 GET /evaluations?limit=20
THEN 响应时间 < 500ms
AND 批量加载关联的 AsyncTask（避免 N+1 查询）
```
