# 验证报告：cost-aware-strategy-selector

- 日期：2026-09-28
- 工作流：Comet Classic tweak（verify_mode: full，含 delta spec）
- 分支：`tweak/20260928/cost-aware-strategy-selector`
- 实现：be73aad（主实现）+ 783ce5a（审查修复）
- 审查方式：独立审查者两轮（全量 diff 审查 requests-changes → 定点复审 approves）

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务完成 | PASS | 13/13 `[x]`（4 个任务组全部完成） |
| 2 | 实现符合 design.md 高层设计 | PASS | 模块划分、单元映射、worker 降级、合并报告、串行路径报错均按设计；resume 回放为设计修订并已同步记录 |
| 3 | Design Doc 一致性 | N/A | tweak 预设无 Superpowers Design Doc |
| 4 | 能力规格场景全部通过 | PASS | 9 个 Scenario 全部有对应测试（见下表） |
| 5 | proposal.md 目标满足 | PASS | 难度映射 + 预算降级 + 默认关闭 + 实验流程不受影响均实现 |
| 6 | delta spec 与 design 无矛盾 | PASS | resume 口径三处（spec/design/README）已同步，validate 通过 |
| 7 | 关联设计文档可定位 | N/A | 无 docs/superpowers/specs 关联文档 |

## Delta spec Scenario 覆盖

| Scenario | 测试 |
|----------|------|
| 题目按难度路由 | `test_problems_route_by_difficulty` |
| 合并报告（含 by_difficulty 保留） | `test_problems_route_by_difficulty`（by_difficulty 断言） |
| 未覆盖难度报错（零模型调用） | `test_unmapped_difficulty_fails_fast`（calls == [] 断言） |
| 参数互斥 | `test_selector_conflicts_with_strategy_flag`、`test_budget_cap_requires_mapping` |
| 达上限后降级 | `test_budget_cap_downgrades_remaining_problems` |
| 未达上限不降级 | `test_problems_route_by_difficulty`（全部 cost_downgraded=False） |
| usage 未知不虚计 | `test_unknown_usage_counted_not_accumulated`、`test_call_free_result_is_not_flagged_unknown` |
| 未启用时行为不变 | `test_non_selector_run_keeps_per_strategy_reports` + 存量 505 测试全绿 |
| resume 回放成本（spec 修订后） | `test_resume_replays_completed_cost_into_cap` |

## 验证命令

- `comet check run cost-aware-strategy-selector build --local -- python3 -m pytest -q` → exit=0（505 passed / 4 skipped，覆盖率 90.75% ≥ 90% 门槛）
- `comet classic openspec -- validate cost-aware-strategy-selector` → valid

## 集成代码审查

- 第一轮（全量 diff，be73aad）：requests-changes——1 IMPORTANT（resume 后成本台账清零，同一任务可多次突破 cap）+ 3 WARNING（并发在途超支窗口未披露；测试与 spec 一致性缺口）+ 5 SUGGESTION。
- 处置：verify-fail 回 build，commit 783ce5a 修复 IMPORTANT 与全部 WARNING 及可安全修复的 SUGGESTION（#5 #6 #7），delta spec/design/README 同步 resume 口径，新增 resume 回放测试与三处断言补强。
- 第二轮（定点复审 783ce5a）：**approves**，无阻断性新问题。确认 resume 回放无双重计数（`unit.result` 非空恰为已完成集合）、非选择器路径不受影响。

## 接受的偏差（SUGGESTION 级，不阻塞）

- fingerprint 变化：`HarnessConfig` 新增字段使升级前创建的任务无法 `--resume`。属 TaskService 既有机制（配置变化即失配），proposal.md Impact 已披露。
- 回退路径（`unit.result is None`）中降级后仍失败的单元显示映射策略而非实际尝试策略；`formal_evaluable` 设置与既有非选择器回退分支存在历史差异。罕见路径，不在 spec 承诺范围，修改会触碰非选择器行为。
- 复合场景"首跑中断 → resume 剩余题全降级"未端到端串联（由 worker 检查与降级测试分段覆盖），留作后续测试增强。

## 结论

全部检查通过，无 CRITICAL/IMPORTANT 未决项。**验证通过（verify_result: pass）**，可进入归档前最终确认。
