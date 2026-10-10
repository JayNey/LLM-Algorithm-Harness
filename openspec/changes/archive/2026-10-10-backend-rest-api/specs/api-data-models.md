## Purpose

数据模型定义 API 请求/响应中使用的标准数据结构和格式，确保前后端之间的数据契约一致性和类型安全。

## ADDED Requirements

### Requirement: 问题数据模型

系统 SHALL 通过以下 JSON 结构表示算法问题：
```json
{
  "problem_id": "string (unique identifier)",
  "title": "string",
  "description": "string",
  "difficulty": "easy|medium|hard",
  "tags": ["string"],
  "constraints": "string (optional)",
  "input_output_mode": "function|stdin_stdout",
  "source_platform": "string"
}
```

#### Scenario: 问题数据被正确序列化
- **WHEN** 系统返回问题数据
- **THEN** 响应包含所有必要字段且类型正确

### Requirement: 评估任务数据模型

系统 SHALL 通过以下结构表示评估任务：
```json
{
  "evaluation_id": "string (unique identifier)",
  "created_at": "ISO 8601 datetime",
  "updated_at": "ISO 8601 datetime",
  "status": "pending|running|completed|failed|cancelled",
  "strategy_names": ["string"],
  "problem_count": "integer",
  "budget_cap_usd": "number (optional)",
  "spent_usd": "number",
  "progress": {
    "completed": "integer",
    "total": "integer",
    "percentage": "number (0-100)"
  }
}
```

#### Scenario: 任务数据包含进度信息
- **WHEN** 客户端获取评估任务信息
- **THEN** 响应包含完整的进度和成本字段

### Requirement: 执行结果数据模型

系统 SHALL 通过以下结构表示单个问题的执行结果：
```json
{
  "result_id": "string (unique identifier)",
  "problem_id": "string",
  "strategy_name": "string",
  "status": "pass|fail|error|timeout",
  "execution_time_ms": "number",
  "cost_usd": "number",
  "output": "string (optional)",
  "error_message": "string (optional)"
}
```

#### Scenario: 结果数据包含执行统计
- **WHEN** 系统返回执行结果
- **THEN** 响应包含执行时间、成本等统计信息

### Requirement: 策略配置数据模型

系统 SHALL 通过以下结构表示策略配置：
```json
{
  "name": "vanilla|chain_of_thought|tree_of_thoughts|few_shot_learning|reflexion|multi_round_feedback|self_consistency",
  "parameters": { /* 策略特定参数 */ }
}
```

#### Scenario: 策略配置被正确验证
- **WHEN** 客户端提交策略配置
- **THEN** 系统验证策略名称有效且参数类型正确

### Requirement: 分页响应数据模型

系统 SHALL 通过以下结构表示列表端点的分页响应：
```json
{
  "success": true,
  "data": {
    "items": [ /* 数据项数组 */ ],
    "total": "integer (总数量)",
    "limit": "integer (每页数量)",
    "offset": "integer (当前偏移)",
    "has_more": "boolean"
  },
  "message": "Success"
}
```

#### Scenario: 分页响应包含元数据
- **WHEN** 客户端请求列表端点
- **THEN** 响应包含 items、total、limit、offset 和 has_more 字段

### Requirement: 错误响应数据模型

系统 SHALL 通过以下结构表示错误响应：
```json
{
  "success": false,
  "error": "error-code",
  "message": "Human-readable message",
  "details": {
    "field": "error description (optional)"
  }
}
```

#### Scenario: 验证错误包含字段详情
- **WHEN** 请求包含无效字段
- **THEN** 错误响应的 details 包含每个无效字段的错误信息

### Requirement: 时间戳格式

系统 SHALL 使用 ISO 8601 格式表示所有时间戳，例如 `2024-10-10T15:30:45Z`。

#### Scenario: 时间戳使用标准格式
- **WHEN** 系统返回包含日期时间的数据
- **THEN** 时间戳遵循 ISO 8601 格式
