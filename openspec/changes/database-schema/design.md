# 设计说明：database-schema

## 决策

1. **SQLAlchemy 抽象 + SQLite 起步、PostgreSQL 可切**：issue 推荐 PostgreSQL，但认证存储已用 SQLite、CI（GitHub Actions）无需额外服务即可跑测试。采用 SQLAlchemy 2.x 统一建模，`api/config.py` 注入 `DATABASE_URL`，默认 SQLite 文件库；生产切 PostgreSQL 仅改连接串，部署侧由 #159 交付。迁移脚本避免方言专属构造，以 PostgreSQL 方言离线生成（`--sql`）作为兼容性检查。
2. **与认证库物理隔离**：沿用 #172 划定的边界，不修改 `api/auth/store.py`；`evaluations.user_id` 存认证用户 id 字符串，不建跨库外键。业务库与认证库使用不同文件/连接。
3. **表设计对齐 issue 草案并裁剪**：`problems`（业务键 `problem_id` 唯一 + 索引、标签/测试用例 JSON 列）、`evaluations`（业务键 `run_id` 唯一、status 枚举、config/结果计数、错误信息）、`evaluation_results`（外键到 evaluations，策略名 + 状态 + 度量 JSON）。`users` 表不建模（由认证库承担）。时间戳统一 UTC。
4. **评估服务改造保持行为兼容**：`TaskState` 保留为运行期缓存（进程内锁与事件回调不变），增量为：创建任务写库、状态/进度变更随事务落库、列表与详情改为读库、启动时将非终态任务标记 failed（附 `interrupted by restart` 原因）。API 响应模型不变，#172 的认证与所有权行为不受影响。
5. **题库导入幂等**：`problems` 以 `problem_id` upsert；现有 `data/*.json` 数据集作为导入源，提供可复用的导入函数（CLI 暴露留待需要时再做，不在本 change 范围）。

## 非目标

- 异步任务队列与执行调度（#149）
- WebSocket 实时进度（#150）
- 结果查询/分析增强 API 与实验/基准管理 API（#155/#156，表结构为其预留扩展）
- 生产部署与数据库服务配置（#159）
- CLI 改造
