## ADDED Requirements

### Requirement: 业务数据持久化

系统 SHALL 使用 SQLAlchemy 定义 `problems`、`evaluations`、`evaluation_results` 业务表，并以 Alembic 管理 schema 迁移；评估任务的创建、状态与进度更新 SHALL 落库，服务重启后任务与已完成结果 SHALL 保持可查询。

#### Scenario: 任务持久化跨重启

- **WHEN** 存在非终态评估任务时 API 服务重启
- **THEN** 任务及其元数据可从数据库查询，被中断的在途任务标记为 failed 且附原因，已完成任务的结果不丢失

#### Scenario: 迁移可从空库复现

- **WHEN** 在空业务库上执行 `alembic upgrade head` 再执行 `downgrade base` 再升级
- **THEN** 全部表与约束创建成功，往返无报错且对象一致

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
