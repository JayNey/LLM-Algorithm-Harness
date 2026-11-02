# persistent-in-app-notifications 验证报告

## 状态

PASS。8/8 任务完成，9 项需求与本次增量场景均有实现和对应测试。没有未解决的 CRITICAL 或 IMPORTANT 问题。归档须等待用户最终确认。

## Summary

| 维度 | 状态 |
| --- | --- |
| Completeness | 8/8 任务，9 项需求均有实现 |
| Correctness | 查询、去重、预算分离、资源链接和前端状态均有测试 |
| Coherence | 遵循 OpenSpec design.md；无独立 Superpowers Design Doc |

## 范围

Issue #328。分支 `tweak/20261101/persistent-in-app-notifications`。基线 `8a6ab918c3f70e38e9c00d4251f9d4343da98120`。规模评估为完整验证：8 个任务、41 个变更文件。`review_mode` 为 tweak 预设的 `off`，因此没有派发自动代码审查；构建、测试、规格对照和安全检查没有跳过。

完成通知写在 `TaskManager.update_task_status` 提交前，而不是分别写在四个业务模块里。评估、实验、基准和 A/B 的完成都经过这次提交，失败会一起回滚；已经完成的历史任务不会被回填。这与 design.md 的同一事务、幂等和不回填历史任务一致。

## 规格对照

- 存储：`in_app_notifications` 与 Alembic `0006`，唯一约束 `user_id + event_key`。清空只写 `cleared_at`，90 天只影响可见性。
- 查询：`/api/v1/notifications` 只返回当前用户，分页未读数是全量，别人的标识返回不存在。批量已读和清空使用服务端时间与请求时间中较早的截止点。
- 事件：四种任务首次完成各一条；中断后重试仍是一条。预算预警在阈值认领时写入，外部发送失败不删除它，保存规则不产生它。
- 内容：参数只保留标识、数量、百分比和金额。资源不可用时链接为空。前端把无时区时间按 UTC 显示，并拒绝站外地址。
- 界面：种子列表已移除。空列表、失败重试和切换账号会清空本地状态。抽屉打开、窗口聚焦和 30 秒轮询会刷新。帮助页和预算页不再把站内通知写成 Mock，并分开描述阈值预警与外部投递。

未改创建评估和题目导入入口。这两项原有场景仍由现有前端测试覆盖。

## 验证证据

- `python3 -m pytest tests/test_in_app_notifications.py tests/test_web_cost_alerts.py --no-cov -q`：20 passed。
- `npm --prefix frontend test`：306 passed，0 failed，0 skipped。
- `npm --prefix frontend run build`：退出码 0，包含 `tsc -b`。已用 `comet state record-check persistent-in-app-notifications build --command "npm --prefix frontend run build" --exit-code 0` 记录。
- `comet classic openspec -- validate persistent-in-app-notifications --type change --strict --no-interactive`：Change is valid。
- `comet guard persistent-in-app-notifications build --apply`：13/13 通过，phase 已进入 verify。

## 审查与限制

没有自动代码审查，原因是 `.comet.yaml` 的 `review_mode: off`。对照实现未发现硬编码密钥、原始服务商错误或跨用户读取。

本 change 的 `design_doc` 为空，没有 `docs/superpowers/specs/` 下的独立设计文档。设计依据是 `openspec/changes/persistent-in-app-notifications/design.md`，与 delta spec 无冲突。

保留既有非阻塞提示：前端生产构建的大 chunk 警告，以及 Pydantic class Config 弃用警告。本次未跑全量后端测试，通知相关后端测试已通过。

## 归档交付

用户于 2026-11-01 明确选择 C：归档、推送当前绑定分支并创建 PR。
