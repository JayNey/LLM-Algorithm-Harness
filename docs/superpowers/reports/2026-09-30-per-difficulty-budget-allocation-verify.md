# 验证报告：per-difficulty-budget-allocation

- 日期：2026-09-30
- 工作流：Comet Classic tweak（verify_mode: full，含 delta spec）
- 分支：`tweak/20260930/per-difficulty-budget-allocation`
- 实现：d9a5f21（主实现）+ 49a646a（审查修复）+ d05594f（复审建议落地）
- 审查方式：独立审查者两轮（全量 diff 审查 requests-changes → 定点复审 approves）

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务完成 | PASS | 12/12 `[x]` |
| 2 | 实现符合 design.md | PASS | DifficultyBudgetMonitor 编排、worker 隔离降级、resume 按难度回放、cost_usd 呈现均按设计；模型级校验为审查修复增量并已同步 |
| 3 | Design Doc 一致性 | N/A | tweak 预设无 Superpowers Design Doc |
| 4 | 能力规格场景全部通过 | PASS | 5 个 Scenario 全部有对应测试（见下表） |
| 5 | proposal.md 目标满足 | PASS | 按难度独立预算、隔离降级、与全局 cap 并存、分布报告均已实现；按标签分配按 proposal 声明不做 |
| 6 | delta spec 与 design 无矛盾 | PASS | validate 通过（ADDED/MODIFIED 结构已修正） |
| 7 | 关联设计文档可定位 | N/A | 无 docs/superpowers/specs 关联文档 |

## Delta spec Scenario 覆盖

| Scenario | 测试 |
|----------|------|
| 单难度触顶隔离降级 | `test_allocation_downgrades_only_that_difficulty` |
| 分配与全局上限并存 | `test_global_cap_downgrades_across_difficulties_with_allocation` |
| resume 按难度回放 | `test_resume_replays_into_difficulty_budgets` |
| 配置校验（非法键/金额/需映射/auto_stop 冲突） | `TestCliOverrides` 5 个新用例 + `TestDifficultyBudgetValidation` |
| 未分配难度无上限 | `test_unallocated_difficulty_is_ignored` + 隔离降级 e2e（easy/hard 不受影响断言） |
| 成本分布呈现（cost_usd + 摘要） | `test_allocation_downgrades_only_that_difficulty`（by_difficulty cost_usd 断言） |

## 验证命令

- `comet check run per-difficulty-budget-allocation build --local -- python3 -m pytest -q --cov-fail-under=0` → exit=0（690 passed / 4 skipped）
- `comet classic openspec -- validate per-difficulty-budget-allocation` → valid
- **覆盖率门禁说明**：pyproject 配置 `--cov-fail-under=90`，当前上游 main 基线覆盖率约 82%（上游 #71–#109 新增约 1500 行代码后未补测试，上游无 CI），该门禁对上游任何分支都不可达。本次验证以全量测试通过为准，覆盖率缺口属 issue #100 范畴，已如实记录。

## 集成代码审查

- 第一轮（全量 diff，d9a5f21）：requests-changes——1 IMPORTANT（config 路径 NaN/inf 金额绕过校验：NaN 致运行中 decimal 崩溃、inf 致预算静默失效）+ 3 WARNING（模型级校验缺失、unknown 按难度计数无测试、降级日志归因误导/刷屏）+ 4 SUGGESTION。
- 处置：verify-fail 回 build，commit 49a646a——`budget_allocation` 升级为 HarnessConfig 模型级 field_validator（空 dict/未知键/非 finite/非正全拒绝，覆盖三条配置路径）；新增 TestDifficultyBudgetValidation；日志归因重构（难度触发日志移至 worker 决策点、mark_trigger_logged 每难度一次；settle 移除误导日志）；cap_for 类型修正。README 补计数口径。
- 第二轮（定点复审 49a646a）：**approves**。三条配置路径封堵实测通过；#86 架构协同（settle 顺序、告警挂全局 monitor、resume 无双重结算）确认正确；复审中的临时探针曾发出 4 个未挂 mock 的真实 API 请求，均被 401 即时拒绝、无计费。
- 复审建议（N1/N2）落地：commit d05594f——全局 `budget_cap_reached_downgrade` 日志以 `monitor.over_cap` 门控（allocation-only 不再误报全局事件），worker 日志中 Decimal cap 以 float 渲染。

## 接受的偏差

- SUGGESTION：resume 回放不恢复降级计数（恢复后摘要从 0 计数）——与 #86 全局行为一致，非本次回归。
- SUGGESTION：`downgraded_problems` 为"该难度全部被降级题数（含全局触发）"——README 已注明口径。

## 结论

全部检查通过，无 CRITICAL/IMPORTANT 未决项。**验证通过（verify_result: pass）**，可进入归档前最终确认。
