## 1. 数据库基础
- [x] 1.1 声明 sqlalchemy/alembic 依赖；新增 `api/db/`（engine/session 工厂、DeclarativeBase、`DATABASE_URL` 配置注入，默认 SQLite）
- [x] 1.2 定义 `problems`/`evaluations`/`evaluation_results` ORM 模型（唯一键、索引、外键、JSON 列）
- [x] 1.3 初始化 Alembic（`api/db/migrations/`）并生成首个迁移；SQLite upgrade/downgrade 往返 + PostgreSQL 方言离线生成通过

## 2. 持久化接线
- [x] 2.1 改造 `evaluation_service`：任务创建/状态/进度落库，列表与详情读库，重启时中断任务标记 failed 附原因；认证与所有权行为不变
- [x] 2.2 题库持久化：`problems` upsert 导入函数，接入现有 JSON 数据集，重复导入幂等

## 3. 验证与交付
- [x] 3.1 数据库层/服务持久化/迁移测试；离线全量套件通过且覆盖率 ≥ 90（门禁不动）
- [x] 3.2 独立审查、修复问题、更新文档（API.md/数据库说明）并撰写验证报告

## 交付门禁
提交并创建关联 #151 的 PR，检查远端 CI，并在验证报告中记录交付结果。
