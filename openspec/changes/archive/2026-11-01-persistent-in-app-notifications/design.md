## Context

通知中心目前由前端种子数组提供三条固定通知，已读和清空只改内存。任务完成已经分别提交在评估、实验、基准和 A/B 的业务状态上；预算外部投递由 `alert_events` 记录，发送失败会释放认领。见 proposal.md 的 Why。

## Goals / Non-Goals

**Goals:**

- 在业务状态提交的同一事务中写入可去重的站内通知，并在恢复时补齐。
- 用现有认证接口提供分页、筛选、全量未读数和带截止时间的批量已读/清空。
- 让通知中心去掉种子数据，并在账号切换后重新加载。

**Non-Goals:**

- 不回填本变更上线前已经完成的历史任务。
- 不新增 WebSocket、外部渠道或系统欢迎通知。
- 不把 paused、failed 或 cancelled 做成站内通知。

## Decisions

1. 业务库新增 `in_app_notifications`。唯一键是 `user_id + event_key`。事件标识为 `task-completed/{evaluation|experiment|benchmark|ab_test}/{entity_id}`，预算为 `budget-alert/{rule_id}/{threshold_pct}/{normalized_cap}`。清空只写 `cleared_at`，90 天只影响可见性，行和事件标识保留。
2. 任务完成通知与首次把业务行提交为 `completed` 的事务一起写入：评估在 `src/tasks/evaluation.py`，实验在实验完成提交，基准在基准运行完成提交，A/B 在 `_finish(..., "completed")`。已经是完成态的恢复路径调用同一个幂等写入。插入冲突视为已存在，不覆盖已读或清空。
3. 预算站内通知在阈值首次被认领的事务里写入，不看外部渠道是否发送成功。发送失败释放 `alert_events` 认领时保留站内行。保存规则不写站内通知。
4. 正文保存消息键和参数，参数只含标识、数量、百分比和已知金额。前端用现有中英文词典渲染。链接在写入时确定：评估 `/evaluations/{id}`，实验 `/experiments/{id}`，基准 `/benchmarks/{suite_id}`，A/B `/ab-tests/{id}`，预算 `/settings/budgets`。列表返回前按当前用户复核资源；不可用时去掉链接并给出原因。
5. API 挂在 `/api/v1/notifications`，使用现有 `current_user` 和 `ApiResponse`。默认每页 20 条，最多 50 条，游标为创建时间加标识。未读数单独计数。批量操作的截止时间取客户端给定时间与事务开始时间中较早者。别人的标识返回不存在。
6. 前端继续用认证 HTTP 客户端。抽屉打开、窗口聚焦和登录后每 30 秒刷新。未读徽章使用全量未读数。账号变化时先清空本地列表。外观切换不清列表。移除 Mock 说明，并改帮助页和预算页里把站内通知说成 Mock 的句子。

## Risks / Trade-offs

- [某个完成提交点漏写通知] → 四种任务各有一条从完成提交到列表的测试。
- [外部发送失败把站内预警一起删掉] → 站内行与 `alert_events` 的失败删除分开测试。
- [轮询有最多 30 秒延迟] → 打开抽屉和窗口聚焦会立即刷新。
- [SQLite 与 PostgreSQL 的并发插入] → 依赖唯一约束，冲突后重读原行。

## Migration Plan

新增 Alembic revision `0006`，`down_revision` 为 `0005`。升级创建通知表和唯一约束；降级只删除该表。不迁移旧的浏览器种子，也不回填历史完成任务。

## Open Questions

无。保留期 90 天、轮询 30 秒和不回填历史任务都已定为本次行为。
