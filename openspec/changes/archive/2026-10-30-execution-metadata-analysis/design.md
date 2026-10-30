## 实现方案
TaskUnit 可选 problem_snapshot 保存 schema_version=1、origin（personal/public/unavailable）和完整 Problem；在首次创建检查点时冻结，旧检查点在开始单元前补齐。恢复与分难度预算判断均使用冻结题目，Worker 返回的 metadata 及结果 metrics.problem_snapshot 只包含标签、难度、schema_version 和源字段，不复制题目到公共库。失败单元同样保留元数据。结果 upsert 保持原快照。
分析使用 metrics.problem_snapshot，显式空或不可用不回退。历史无快照沿用当前公共题库标签/已有 metrics.difficulty 的兼容路径，无法恢复个人题历史，不读取当前个人题伪造历史。文档明确此路径非历史快照。SQL 筛选与 Python 聚合规则一致，SQLite/PostgreSQL 均支持。雷达以题目 ID 加快照标签身份关联每个执行版本，同一版本多策略只计一份题目，结果仍每单元计入。
## 验证
覆盖纯个人、同 ID 覆盖、空标签、题库修改、来源字段、缺失失败、重复写入、多策略和暂停恢复；实际 Worker/TaskService/数据库到 HTTP 接口链路用替代 LLM/沙箱隔离网络。
