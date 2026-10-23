# preserve-cost-model-name 验证报告

结论：PASS。实现提交：da7542a；分支：comet/preserve-cost-model-name。

## 规模与检查

自动统计 14 个文件包含 Comet 状态、快照与文档，实际业务改动仅 1 个源码文件及 1 个测试文件、3 项任务、0 delta spec。按 comet-verify 允许的覆盖机制选择 light。

1. PASS：tasks.md 三项任务均已完成；RED 两项业务断言失败，GREEN 两项回归通过。
2. PASS：最终 diff 与 proposal/design/tasks 一致，仅修复成本拆分和优化报告的模型维度。未提交改动均为本 change 的 Comet 状态及本报告。
3. PASS：验证阶段重新执行 `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/preserve-model-wheel` 成功构建 wheel，退出码 0。
4. PASS：验证阶段重新执行 `pytest tests/test_api_cost.py tests/test_cost_optimizer.py tests/test_pricing.py tests/test_cost_alert.py tests/test_cost_estimation.py tests/test_pareto.py --no-cov -q`，113 passed，退出码 0。覆盖真实模型区分、同模型同策略合并、null/空字符串历史回退、benchmark 混合、用户隔离及时间窗口。未运行全仓库测试；5 条警告均为既有 Pydantic 配置弃用提示。
5. PASS：无新增密钥、外部调用或 unsafe 操作；用户过滤保持不变。`black --check api/services/cost_service.py tests/test_api_cost.py`、`ruff check api/services/cost_service.py tests/test_api_cost.py` 与 `git diff --check` 均通过。
6. PASS（按配置跳过自动审查）：hotfix 的 review_mode=off，不派发代码审查。

## 根因与兼容性

_spend_rows 使用已保存的 Evaluation.model，仅为空时回退 evaluation-run。优化报告以 (model, strategy) 聚合，输出该模型；两个丢弃真实模型名的硬编码均已移除。保留原成本、准确率公式及筛选条件，无 API 或 schema 变更。

`comet classic openspec -- validate preserve-cost-model-name --strict` 通过。此修复恢复已有模型维度语义，不修改 spec 验收要求，skip_specs=true。

branch_status 保持 pending，等待用户确认归档与交付方式。Comet task 插件因全局锁文件权限失败不可用，不影响验证。

## 归档交付确认

用户选择 C：确认归档、立即推送绑定分支并创建 PR。归档已完成，branch_status=handled 记录该交付选择；推送与 PR 结果以最终交付记录为准。
