# 内部清理任务越权提交修复验证

## 结论

PASS。公开任务创建只接受四种业务类型与现有 Celery 名称的精确配对。内部清理、未知任务和不匹配请求均在落库和消息发布前返回 403。Celery Beat 内部清理仍保持原行为。

## 根因与失败证据

旧实现把客户端 Celery 任务名直接交给 TaskManager；两个清理 worker 按全表删除终态记录。新增 HTTP 测试使用独立 SQLite、普通用户 Principal 和实际清理 worker，由模拟发布器同步消费。

首次运行 `python3 -m pytest tests/test_task_submission_authorization.py -q --no-cov`：14 failed / 4 passed。10 个内部清理攻击场景均返回 201、发布 1 条消息并删除攻击者和受害者的两条已完成记录。另 4 个未知/类型错配请求也错误返回 201。

加入路由允许列表后，同一命令：18 passed。攻击场景均返回 403，发布次数为 0，两条原记录均保留，无新任务记录。四种合法配对均返回 201。

## 检查结果

1. 任务完整性：tasks.md 三项全部完成。
2. 改动范围：生产代码仅 `api/routes/tasks.py`；测试仅新增 `tests/test_task_submission_authorization.py`，其余为当前 change 产物与本报告。
3. 编译：`python3 -m compileall -q api src`，退出码 0。
4. 相关测试：以下命令 172 passed，退出码 0。

   ```text
   python3 -m pytest tests/test_task_submission_authorization.py tests/test_tasks_api.py tests/test_task_manager.py tests/test_async_task_submission.py tests/test_tasks_cleanup.py tests/test_cleanup_tasks.py tests/test_celery_tasks.py tests/test_api_documentation.py tests/test_api_errors.py -q --no-cov
   ```

5. 安全与边界：精确映射先于 enqueue_task；未知名称和类型默认拒绝，无前缀放行、无落库或发布副作用，无新增密钥或危险执行。检查公开路由仅有此一处 enqueue_task 路径。
6. 自动集成代码审查：按 hotfix 默认 `review_mode: off` 跳过；已检查最终 diff 的授权顺序与允许列表边界。

附加检查：`ruff check api/routes/tasks.py tests/test_task_submission_authorization.py`、`black --check api/routes/tasks.py tests/test_task_submission_authorization.py`、`git diff --check`、`comet classic openspec -- validate fix-internal-cleanup-authorization --strict` 均退出码 0。

## 验证边界

运行相关测试集，未运行全仓测试或覆盖率门槛。测试以模拟消息发布器隔离 broker，攻击复现实际执行清理 worker。现有 5 条 Pydantic 弃用警告不属于本次变更。业务对象归属及任务参数授权未作扩展。
