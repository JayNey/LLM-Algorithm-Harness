# failed-call-budget 验证报告

结论：PASS。Issue #350 的验收条件已满足，可进入归档确认。

## 完整性与一致性

- 2/2 tasks 已完成，单一既有能力 experiment/budget-comparison 的 delta 已核对。
- 准入后立即记录逻辑调用数，响应只结算 token；异常原样传播，不退回名额。预算未配置时仍计数，未开始 problem 时保持透传。
- Self-Consistency 单独处理 BudgetExhausted，立即停止，保留已完成候选与投票结果，终态及 ledger 记录明确预算原因，failure_category 为空。
- 设计与 delta 无漂移。tweak 按流程无额外 Superpowers Design Doc/plan，此项不适用。
- 仅 5 个业务/测试/指南文件；其余变更为 Comet 生成的状态、快照与规划产物，无跨模块架构协调或公共接口扩展。

## 场景覆盖

- 调用数上限：TestBudgetTracker.test_call_budget_blocks_after_limit、TestBudgetedLLMClient.test_blocks_call_when_budget_exhausted。
- token 结算与未知 usage：test_token_budget_counts_known_usage、test_usage_missing_flags_unsupported_token_budget。
- 首次异常即计数且不重复进入 inner：test_failed_call_is_charged_on_admission，含无预算记账与 finalize。
- 首次成功及真实客户端缓存命中：test_success_or_cache_hit_consumes_one_call（缓存与非缓存分支）。
- 内部 SDK retries：test_sdk_retries_share_one_logical_call，真实 LLMClient 三次离线 SDK attempts 对应一次逻辑调用。
- 实际多候选入口：test_self_consistency_stops_after_provider_failure，max_calls=1/2，保留 provider failure 迭代，阻止后续 inner 调用，状态、分类、错误与 ledger 均核验。
- 时间预算与既有实验指标、报告路径由完整实验测试回归覆盖。

## 新鲜验证证据

- RED：新增 5 项核心回归在修改生产代码前均失败，直接暴露准入漏记与候选超限。
- GREEN：`pytest tests/test_experiment.py tests/strategies tests/test_llm_client.py -o addopts='' -q`：111 passed，5 个既有收集/弃用警告，0 failures。此次针对相关测试运行，不宣称全仓覆盖率达标。
- `black --check src/budget.py src/models.py src/strategies/self_consistency.py tests/test_experiment.py`：通过。
- `ruff check src/budget.py src/models.py src/strategies/self_consistency.py tests/test_experiment.py`：通过。
- `mypy src/budget.py src/strategies/self_consistency.py`：通过（2 source files）。
- `git diff --check`：通过。
- `comet classic openspec -- validate failed-call-budget --strict`：通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/issue350-dist`：成功生成 wheel。环境无 python -m build，采用现有 pip/setuptools。

## 集成代码审查

按 requesting-code-review 技能派发只读独立 reviewer，覆盖 4be727e^..4be727e、tasks、设计与 delta。未发现 P0/P1/P2 正确性、安全或边界问题。生产环境的 record 调用方只有预算包装器，无遗留直接调用不兼容；投票结果在标记终态后保留。可选增加成功候选后遇到 provider failure 的独立测试，现有投票测试与静态审查已覆盖保留机制，无需接受行为偏差。

## 边界与归档输入

max_calls 限制逻辑 generate，包含失败和缓存；SDK attempts 受客户端重试配置单独限制，不保证收费上限。没有可靠 usage 的失败调用不虚构 token 或费用。使用离线替身，无付费 provider 请求。

当前分支 comet/failed-call-budget；实现已提交 4be727e。未提交差异仅为当前 change 的任务验收、Comet 状态和本验证报告，可在归档交付时精确纳入。branch_status 保持 pending。等待用户一次确认归档及本地/推送/PR 方式。
