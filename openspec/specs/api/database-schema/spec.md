# api/database-schema Specification

## Purpose
TBD - created by archiving change database-schema. Update Purpose after archive.

## Requirements

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

### Requirement: 题库入库与幂等导入

系统 SHALL 提供 `problems` 表及来自现有 JSON 数据集的导入入口；重复导入 SHALL 不产生重复行（按 `problem_id` upsert），`problem_id` 上 SHALL 有唯一索引支撑查询。

#### Scenario: 重复导入幂等

- **WHEN** 同一 JSON 数据集连续导入两次
- **THEN** `problems` 行数不增加，字段更新以最新导入为准，按 `problem_id` 查询命中唯一行

### Requirement: 数据库双栈与隔离边界

系统 SHALL 通过配置注入的 `DATABASE_URL` 连接业务库（开发/测试默认 SQLite，生产可配置 PostgreSQL）；业务库 SHALL 与认证存储保持物理隔离，`evaluations.user_id` 仅以字符串引用认证用户标识，不建跨库外键。

#### Scenario: 切换目标数据库方言

- **WHEN** 以 PostgreSQL 方言离线生成迁移 SQL（`alembic upgrade --sql`）
- **THEN** 生成成功且不含 SQLite 专属构造；默认 SQLite 路径下应用照常启动

### Requirement: 站内通知持久化

系统 SHALL 用 Alembic 在业务库增加站内通知表。每条记录 SHALL 保存所属用户、类型、稳定事件标识、创建时间、已读时间、清空时间和站内资源引用。`user_id` SHALL 只作为认证用户的不透明字符串，不建跨库外键。同一用户与同一事件标识 SHALL 有唯一约束。清空和超过保留期 SHALL NOT 删除事件标识，以免旧事件重放重新插入。

#### Scenario: 迁移可从空库复现

- **WHEN** 在空业务库上执行到最新迁移、回退再升级
- **THEN** 站内通知表与唯一约束可重复创建且不破坏既有业务表

#### Scenario: 重复事件不能插入第二行

- **WHEN** 同一用户和同一事件标识被并发写入
- **THEN** 只保留一行，后写的一方不覆盖已清空或已读状态
