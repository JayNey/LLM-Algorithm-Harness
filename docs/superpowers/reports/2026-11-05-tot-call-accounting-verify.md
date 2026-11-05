# ToT 调用记账验证

日期：2026-11-05。Change：tot-call-accounting。实现提交：7abfde9。结论：PASS。

## 完整性
两个任务全部完成。业务改动为 ToT、StrategyBase 类型声明和 ToT 测试三个文件；其余为本 change 的 OpenSpec/Comet 产物。没有新增架构、外部 API 或数据模型。Tweak 不产生独立 Superpowers Design Doc/plan，设计依据为 change/design.md。verify_mode 为 full，review_mode 按 tweak 默认 off，未派发独立代码审查。

## 正确性与场景映射
- Generation and evaluation settlement：test_two_calls_settle_and_match_experiment_ledger 验证两次调用、300 token、$0.02，Harness 汇总、实验 ledger 和 $0.01 cap 一致。
- Branching and pruning：test_multilevel_pruning_keeps_every_call 的 BFS/DFS 两种遍历验证 6 次调用/900 token/$0.06；test_empty_or_pruned_search_retains_cost 验证无代码或全剪枝仍保留消耗。
- Failures and budget stops：test_model_failure_preserves_prior_calls 验证生成和评分失败；test_invalid_score_still_retains_response 验证解析异常；两个预算测试验证拒绝前后日志及预算状态；test_strategy_reuse_does_not_carry_cost 验证多问题隔离。
- Missing usage and pricing：test_unknown_and_zero_semantics 区分缺失用量、未知价格和已知零价。

## 验证证据
- RED：新增记账测试初次运行 12 failed/1 passed，固定两次响应仍为 0 token，确认根因。
- GREEN：python3 -m pytest tests/test_tree_of_thoughts.py tests/test_cost_strategy.py tests/test_budget_guard.py tests/test_budget_coverage.py tests/test_benchmark_run_budget.py tests/test_cost_estimation.py --no-cov -q：129 passed。包含 15 个新增用例。该命令仅验证相关范围，不代表全仓覆盖率达标。
- python3 -m black --check src/strategy_base.py src/strategies/tree_of_thoughts.py tests/test_tree_of_thoughts.py：通过。
- python3 -m ruff check 同上三个文件：通过。
- python3 -m mypy src/strategies/tree_of_thoughts.py --ignore-missing-imports --follow-imports=silent：通过。修正了共享 helper 已支持 None 响应但声明不匹配的问题，改为 Sequence[LLMResponse | None]，不改变运行时行为。
- comet classic openspec -- validate tot-call-accounting --strict：通过。
- python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/tot-349-verify：通过。环境缺少 python -m build，改用现有 setuptools/pip 完成 wheel 构建。
- git diff --check：通过。

## 一致性与边界
调用日志在搜索入口重置；成功响应先保存后解析；每次调用对应一条轨迹，生成多个节点不重复计账；剪枝不删除调用。失败保留错误并标记未知用量；预算拒绝不产生虚假调用。沿用共享结果脱敏与费用处理，无新增密钥或外部调用。实现与 proposal、design、delta spec 一致，无待接受偏差。测试使用模型和沙箱替身，未访问真实模型账单；已有 Pydantic 弃用告警不影响结果。

当前未提交内容均为验证状态和本报告；branch_status 保持 pending，主 spec 同步和归档等待最终确认。
