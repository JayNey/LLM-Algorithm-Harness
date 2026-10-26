# 预算执行控制验证报告

结论：PASS。预算已接入 Web 评估 worker；实现与精简设计及 delta spec 一致。

## 完整性

三项任务已完成。变更为单一 Tweak，用户已选择 A2，知悉跨模块协调并使用独立分支。两份实现文件与两份测试文件完成业务变更；其余文件为 Comet/OpenSpec 方案、状态及验证证据。无数据库迁移、新 HTTP API 或新依赖。

## 验证命令与结果

- `pytest tests/test_celery_tasks.py tests/test_api_cost.py tests/test_evaluation_service_async.py tests/test_evaluation_async_flow.py tests/test_evaluation_workflow_contract.py tests/test_api_evaluations.py tests/test_api_evaluation_results.py tests/test_evaluation_results_service.py tests/test_evaluation_result_iterations.py tests/test_user_evaluation_concurrency.py tests/test_cost_strategy.py tests/test_task_service.py --no-cov -q`：275 passed，5 个已有 Pydantic class Config 弃用警告。该次验证为相关回归，未运行全仓测试及全仓覆盖率门槛。
- `ruff check api/services/cost_service.py src/tasks/evaluation.py tests/test_celery_tasks.py tests/test_api_cost.py`：通过。
- `black --check api/services/cost_service.py src/tasks/evaluation.py tests/test_celery_tasks.py tests/test_api_cost.py`：通过。
- `git diff --check`：通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir /tmp/budget-execution-wheel`：成功构建 wheel。
- `comet classic openspec -- validate budget-execution-control --strict`：通过。

## 正确性：场景映射

- 全局触顶暂停：`test_personal_budget_controls_actual_dispatch[pause]`、`test_exhausted_history_stops_before_first_call`，下一单元不执行且数据库及检查点保留结果。
- 分难度触顶：`test_difficulty_cap_only_affects_matching_units`，easy 耗尽后 hard 原策略仍执行；回到 easy 才触发暂停或降级。
- 实际降级与追溯：`test_personal_budget_controls_actual_dispatch[downgrade]`、`test_multiple_strategies_keep_distinct_results_after_downgrade`，执行 vanilla，原单元身份稳定，保存 executed_strategy/cost_downgraded。
- 原约束优先：`test_task_cap_overrides_downgrade`、`test_manual_pause_wins_over_personal_downgrade`。
- 恢复重新检查：`test_resume_rechecks_updated_budget_without_rebilling`，预算不足恢复仍暂停，提高额度后只执行剩余题目，总成本为 0.02。
- 用户隔离与兼容：`test_other_user_budget_and_spend_do_not_affect_execution`、既有无个人预算评估集成测试。
- Web 保存接入：`test_web_saved_budget_controls_worker` 经真实 HTTP 保存预算、创建和启动评估，再运行真实 TaskService 调度；pause/downgrade 两个分支均通过，HTTP 任务状态和累计用量与执行一致。模型执行和 sandbox runtime 为外部边界替身，无真实计费。
- 成本口径：`test_execution_snapshot_uses_actual_difficulty_and_owner`、`test_benchmark_history_counts_only_completed_owned_runs`；金额使用 Decimal 比较和累加，`test_decimal_boundary_does_not_dispatch_an_extra_unit` 验证十次 0.01 达到 0.10 即暂停。

## 一致性与安全

主线程读数据库并选择策略；执行线程只读单元选择，未捕获 session。沿用原单任务预算暂停、手动暂停和取消机制。每次派发前读取最新个人预算。所有个人成本查询均按 owner 过滤。未引入密钥或外部消息发送。

`review_mode: off` 为 Tweak 初始化状态，依协议未派发自动代码审查；仍完成最终 diff 人工式核对、安全边界与规格一致性检查。Tweak 按入口协议省略完整 Superpowers Design Doc/plan，因此对应完整设计文档检查不适用；已核对 change/design.md。

## 调试闭环

最初新增测试复现个人预算不生效；实现后发现恢复测试修改了 worker 已关闭 session 的 detached 对象，修正测试为 merge 后提交。端到端测试先定位到 worker 缺少测试 AuthSettings，随后检查点显示测试题描述不满足最小长度；补齐真实配置与合法输入。金额边界测试复现浮点累加低于阈值后改用 Decimal。最终相关回归全部通过。

## 已明确的行为边界

控制发生在评估单元边界，不中断在途调用；并发评估不预留共享额度，因此不是跨任务硬金额限流。全局累计沿用评估与已完成 benchmark 口径；本次接入对象为 Web 评估 worker。分难度使用已持久化结果的实际已知成本，与页面保留的比例估计口径不同；缺少难度仅参与全局成本，未知费用不虚构。降级元数据保存在结果 metrics，不改造前端结果展示。

未发现未解决的 CRITICAL、IMPORTANT 或规格漂移。
