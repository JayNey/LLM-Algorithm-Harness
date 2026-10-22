## 问题与根因

普通用户可以通过 `POST /api/v1/tasks` 指定任意 Celery 任务名。接口只检查登录身份，直接把客户端任务名交给 TaskManager 发布。内部 `cleanup_old_tasks` 和 `cleanup_task_count` 按全表清理，没有用户范围，因此公开提交入口可触发跨用户删除。

## 修复目标

- 公开接口只接受现有四种业务任务与其精确 Celery 名称的合法配对；内部、未知和不匹配任务返回 403。
- 拒绝发生在创建数据库记录和发布队列消息之前。
- 保持已有业务任务入队顺序及 Celery Beat 内部清理行为。

## 影响范围

仅修改 `api/routes/tasks.py` 与授权回归测试，无新接口、依赖或数据库 schema。修改 `async-task-queue` 中通用任务创建要求的验收场景。

## 复现证据

`python3 -m pytest tests/test_task_submission_authorization.py -q --no-cov`：旧实现 14 failed / 4 passed。10 个清理攻击场景均返回 201、发布 1 条消息；测试用真实清理 worker 同步消费后，攻击者与受害者两条已完成记录均被删除，仅留下新建 pending 记录。另 4 个未知/类型不匹配场景同样错误返回 201。4 个合法业务配对通过，证明测试环境与正常提交链路可用。
