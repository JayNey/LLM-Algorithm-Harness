# 未知费用与美元预算验证

关联 GitHub #481。实施提交为 `583316fa`。

## 规格覆盖

- CLI 在配置模型缺价时保留待执行单元。缺少用量或发生无法核算的请求后，阻止后续调用及重试。恢复按已保存单元重建预算状态。覆盖用例为 `test_cap_handles_unpriceable_calls` 和 `test_cli_stops_later_provider_attempts`。
- Web 在派发和 SDK 重试处检查任务美元上限。预算暂停后重复恢复不会重新调用已记录单元。覆盖用例为 `test_run_evaluation_task_unknown_pricing_honest` 和 `test_capped_web_generation_stops_after_unaccountable_attempt`。
- 已知部分仍纳入小计。有明确用量的显式零价继续派发。覆盖用例为 `test_mixed_cost_keeps_known_subtotal` 和 `test_web_pricing_drives_real_cost_and_budget`。
- Web 任务响应和详情传递可空的已知金额、未知费用单元数及预算状态。API 回归验证了金额未知和已知零美元的区别，前端客户端测试验证了两种值的读取。
- 实现符合当前 tweak 的 `design.md`。使用已有定价解析、检查点和结果行，未引入数据库迁移。按用户确认继续单一 tweak 变更。

## 执行结果

- 后端相关回归 502 项通过，含 CLI、Celery、评估 API、结果、定价和费用监控。
- 前端测试 357 项通过。生产构建与 ESLint 通过。Chrome 详情夹具验证 27 项断言通过，确认未知金额、未知单元数和预算状态可见。
- OpenSpec 严格验证通过。Ruff、改动文件的 Black 检查、编码检查与 Git 差异检查通过。
- 全量 mypy 在基线和本分支均报告相同的 4 项既有错误，位于 `api/files/parsing.py`、`api/progress.py` 和 `api/services/cost_alert_service.py`。
- 自动代码审查沿用 tweak 的 `review_mode: off`。已按规格逐项检查实现和回归证据。

## 结论

PASS。缺价、运行中未知费用、零价和恢复的验收场景均通过。
