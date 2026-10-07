# 验证报告：incremental-evaluation-fixes

- 日期：2026-10-07
- 工作流：Comet Classic tweak（verify_mode: full，含 delta spec）
- 分支：`tweak/20261007/incremental-evaluation-fixes`
- 实现：1752619
- 审查方式：独立审查者全量审查

## 背景

issue #87 已由 PR #122 关闭，但本 change 审计发现其主流程集成存在三个缺陷，导致增量模式从未真正生效（每次静默回退全量评估）。本 change 修复缺陷并以端到端测试证明闭环。

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务完成 | PASS | 8/8 `[x]` |
| 2 | 实现符合 design.md | PASS | 三个缺陷的修法均按设计落实 |
| 3 | Design Doc 一致性 | N/A | tweak 预设无 Superpowers Design Doc |
| 4 | 能力规格场景全部通过 | PASS | 3 个 Requirement 全部 Scenario 有对应测试 |
| 5 | proposal.md 目标满足 | PASS | 三个缺陷修复 + e2e 闭环证明 |
| 6 | delta spec 与 design 无矛盾 | PASS | validate 通过 |
| 7 | 关联设计文档可定位 | N/A | 无 docs/superpowers/specs 关联文档 |

## Delta spec Scenario 覆盖

| Scenario | 测试 |
|----------|------|
| 识别变化题目 | `test_second_run_evaluates_only_changed_and_merges`（Unchanged 2 / New 1 / Modified 1 断言） |
| 无匹配历史运行 | `test_no_matching_run_falls_back` |
| 只评估变化题目 | `test_second_run_evaluates_only_changed_and_merges`（合并 2 复用 + 2 新执行；仅 p2/p4 被执行） |
| 历史结果损坏回退 | `test_corrupted_history_falls_back_to_full` |
| 合并报告指标完整 | `test_second_run_evaluates_only_changed_and_merges`（total=4、estimated_cost_usd>0、by_difficulty、avg_attempts） |

## 修复的缺陷

1. `ProblemLoader.filter_problems` 不支持 `problem_ids` → 增量选集 TypeError 静默回退全量 → 新增白名单参数。
2. `load_historical_results` 期望 `{strategy: [results]}` 而 `result_path` 指向 summary.json（形状不匹配）→ 改为读取 run 目录内 `*_results.json`。
3. 合并报告 `estimated_cost_usd=0.0`/`avg_attempts=1.0` 硬编码 → 从合并结果真实重算（成本/难度分布/formal 指标）。
4. 审计追加发现：首跑从不记录历史（历史更新仅挂在增量合并分支）→ 增量启用时任何成功运行都记录指纹，供下次匹配；`find_matching_run` 要求指纹完全相等 → 与增量语义矛盾，改为策略+模型匹配（变化量由 `should_use_incremental` 把关）；`incremental_context["history_path"]` 在首跑为 None 时下标崩溃 → 改用局部变量。

## 验证命令

- `comet check run incremental-evaluation-fixes build --local -- python3 -m pytest -q --cov-fail-under=0` → exit=0（1095 passed / 4 skipped，覆盖率 90.73%）
- `comet classic openspec -- validate incremental-evaluation-fixes` → valid
- 上游存量测试同步更新：test_detector/test_merger_integration 两处断言旧（错误）语义 → 已按新契约修正

## 集成代码审查

（待独立审查结论补记。）

## 结论

（待审查后填写。）
