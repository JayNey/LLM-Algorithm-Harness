## MODIFIED Requirements

### Requirement: 业务数据持久化

系统 SHALL 使用 SQLAlchemy 定义 `problems`、`evaluations`、`evaluation_results` 业务表，并以 Alembic 管理 schema 迁移；`evaluations` SHALL 持久化真实执行所需的 `model` 标识；评估任务的创建、状态与进度更新 SHALL 落库，服务重启后任务与已完成结果 SHALL 保持可查询。

#### Scenario: 任务持久化跨重启

- **WHEN** 存在非终态评估任务时 API 服务重启
- **THEN** 任务及其元数据可从数据库查询，被中断的在途任务标记为 failed 且附原因，已完成任务的结果不丢失

#### Scenario: 迁移可从空库复现

- **WHEN** 在空业务库上执行 `alembic upgrade head` 再执行 `downgrade base` 再升级
- **THEN** 全部表与约束创建成功，往返无报错且对象一致

#### Scenario: 评估模型标识落库

- **WHEN** 创建评估时提供了 `model`
- **THEN** `evaluations.model` 持久化该值，worker 执行时可读回用于解析 LLM 凭证；在既有库上执行迁移后该列可用且不破坏已有行
