# PR #330 CI 修复与 issue #328 复核

本次独立处理，不进入或修改 Comet workflow 状态。复核基线为 PR head `c0eeae764dfe13fec8f55d741aa6a2e8507e1e6c`。

## 原 CI 失败原因

读取 GitHub Actions run `41285681649` 的 Type Check 和 Ubuntu Python 3.11 作业日志：

- mypy：通知服务存在 10 项类型错误，包括变长条件元组、SQLAlchemy Result/Select 类型、复用 ORM 变量和动态资源模型类型。
- pytest：`test_every_registered_endpoint_has_an_explicit_happy_path_case` 缺少 5 个新增通知端点。原 CI 覆盖率已达到 src 91.49%、API 94.69%，覆盖率不是这次失败原因。

修复明确类型及 ORM 变量，不关闭检查或降低覆盖率。将 5 个端点加入既有契约测试，因此同时覆盖认证要求、HTTP 返回与服务调用参数。

## 额外发现及修复

- 时间序列化截断微秒：同秒通知跨页会遗漏，服务端快照截止时间也可能漏处理快照前已存在的通知。保留完整微秒精度；3 个新增回归在修复前均失败，修复后通过。
- SQLite SAVEPOINT：没有先行 DML 时，释放 savepoint 可独立提交，外层回滚留下通知。在创建 savepoint 前保证 SQLite 已开启物理事务；新增外层中断回滚测试先失败后通过。
- 中断恢复原测试没有设置 `Evaluation.async_task_id`，未执行真实业务状态同步。现建立关联，同时断言业务状态、任务状态、通知一并回滚，重试一并提交。

## issue #328 对照

- 持久化存储与 API：迁移、90 天可见期、类型/已读筛选、游标分页、全量未读和当前用户归属限制均已实现。
- 四类完成事件：evaluation、experiment、benchmark、ab_test 通过 TaskManager 的事务写入通知；测试覆盖四类事件及重试幂等。
- 预算语义：阈值认领时生成站内通知，保存规则不生成，外部投递失败不删除站内预警；沿用预算 Dispatcher 及相关回归。
- 去重与清空：唯一业务事件键、清空墓碑、并发投递及清空后并发重放均有回归。批量操作测试在新通知写入未提交、批量 UPDATE 已到达时释放写入事务，检查截止范围外通知不被处理。
- 跨会话：真实任务完成后通过认证通知 API 获取；另一用户无法读取或修改；再次登录看到持久已读与清空；旧客户端看到一致结果。
- 前端：真实 API gateway 替代 seed，30 秒轮询/聚焦/打开抽屉刷新，认证会话 marker 改变时 key 重建通知中心；store 测试覆盖加载、失败重试、分页、旧响应和账号隔离。
- 内容与导航：参数白名单脱敏，资源不存在/非归属时无链接，前端拒绝站外链接；中英文及 API 文档已更新。

结论：功能主体已覆盖 issue 的要求，修复补充了此前漏测的正确性边界。不能将原报告的 PASS 当成所有验收项已实测：本次未进行真实浏览器的移动端抽屉/键盘焦点人工验收，亦未运行四业务真实 Celery Worker 到浏览器页面的端到端测试。PostgreSQL 并发行为未实测；数据库迁移包含 PostgreSQL 离线 SQL 校验，实际并发回归使用 SQLite。

## 验证证据

- `python3 -m pytest tests/test_in_app_notifications.py tests/unit/test_api_endpoints.py tests/test_web_cost_alerts.py --no-cov -q`：894 passed。
- 最新增强后的 `python3 -m pytest tests/test_in_app_notifications.py --no-cov -q`：15 passed，含真实重叠事务批量操作。
- `/tmp/pr330-venv/bin/python -m mypy src/ --ignore-missing-imports`：100 个源文件通过。临时 venv 对齐 CI 的 mypy 2.4.1、SQLAlchemy 2.1.6、redis 8.1.0 及类型桩，不改变项目依赖配置。
- `npm --prefix frontend test`：306 passed。
- `npm --prefix frontend run build`：通过；存在既有 chunk 大小提示。
- `ruff check .`、`black --check .`、`python3 scripts/find_missing_encoding.py`：通过。
- `/tmp/pr330-venv/bin/python -m pytest -m "not online"`：3679 passed、11 skipped，耗时 505.79 秒，总覆盖率 92.81%。跳过项沿用现有测试条件。src 覆盖率 91.50%（门槛 90%），API 覆盖率 94.81%（门槛 81%），均通过。

最初在沙箱内执行全量测试，HTTP 测试绑定本地端口出现 `PermissionError`，已停止该次运行并在允许本地 HTTP 的环境重新执行；该环境问题未通过修改测试规避。
