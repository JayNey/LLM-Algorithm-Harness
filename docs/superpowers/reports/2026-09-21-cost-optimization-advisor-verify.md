# 验证报告：cost-optimization-advisor

- 日期：2026-09-22
- 分支：`tweak/20260921/cost-optimization-advisor`（基于 upstream/main `a99a0b2`，含已合并的 #46/#65）
- 验证模式：full（1 个 delta spec 能力、13 个任务）
- review_mode：off（tweak 预设默认；以任务级检查 + 全量测试 + 手算对账夹具作为集成验证手段，未安排独立审查者）

## Summary

| 维度 | 状态 |
|------|------|
| Completeness | 13/13 任务完成；delta spec 4 个需求 8 个场景全部有实现与测试 |
| Correctness | 排名/三目标/预算优化全部按手工 fixture（4 组合、比例 5.0/3.5/2.25）对账通过 |
| Coherence | 纯只读分析命令，复用 #65 的 comparison.json 数据结构，不触碰执行路径 |

## 检查项结果

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部勾选 | PASS | 入口状态 13/13 |
| 2 | 实现符合 design.md | PASS | `src/cost_optimizer.py`（排名/推荐/优化器）、`src/main.py` optimize 子命令、产物 optimization.json + OPTIMIZATION.md |
| 3 | OpenSpec 校验 | PASS | `openspec validate` → valid |
| 4 | 能力规格场景通过 | PASS | 见场景清单；全量 470 passed, 4 skipped |
| 5 | proposal.md 目标满足 | PASS | 性价比排名、三目标推荐、预算优化器、CLI 与产物、文档全部落地 |
| 6 | delta spec 与 design 无矛盾 | PASS | 无 Implementation Divergence |
| 7 | 关联设计文档可定位 | N/A | tweak 流程无 docs/superpowers/specs 设计文档 |
| 8 | Runtime 构建/测试证据 | PASS | `comet check run build` exit=0（81e4766a） |

## Spec 场景覆盖清单

| 场景 | 测试证据 |
|------|----------|
| 排名按性价比降序 | `test_ranking_sorted_by_ratio_descending`（5.0 > 3.5 > 2.25 手算） |
| 成本未知排除 | `test_cost_unknown_excluded_and_annotated`（mystery-model 标"成本未知"） |
| 三种目标各自成立 | `test_highest_accuracy_*` / `test_best_value_*` / `test_lowest_cost_respects_min_accuracy` |
| 无满足约束方案 | `test_lowest_cost_infeasible_when_nothing_clears_bar`（feasible=false + 说明） |
| 预算内生成推荐 | `test_layers_pick_best_throughput_within_budget`（每层模型、coverage、成本上限断言） |
| 历史数据不足时标注 | `test_layers_without_history_are_annotated`、`test_min_accuracy_filters_layers` |
| CLI 完整执行 | `test_cli_optimize_end_to_end`（optimization.json/OPTIMIZATION.md/stdout 一致） |
| 输入无效时报错 | `test_cli_optimize_missing_comparison_fails`（退出码 1，无产物残留） |

## 手算对账

- fixture（每组合 10 题）：budget-model 5 过/$1.00 → 性价比 5.0；mid-model 7 过/$2.00 → 3.5；pro-model 9 过/$4.00 → 2.25；mystery-model 无定价 → 排除。
- 三目标：highest_accuracy → pro（0.9）；best_value → budget（5.0）；lowest_cost@0.6 → mid（0.7 达标且 $2.00 < $4.00）✓。
- 分层（预算 $10，min 0.5）：easy → budget（0.75 层准确率，throughput 胜出）；medium → budget（唯一有历史）；hard → mid（throughput 3.5 > pro 2.25）；估算成本 $1.60 ≤ $10，加权准确率 0.5833，覆盖 12 题 ✓。

## 过程中发现并修复的问题

1. **IMPORTANT**：`optimize_budget` 的行过滤误用 `_accuracy()`（读 combo 的 `pass_rate_over_total` 键）于 row 字典（键为 `accuracy`），导致 rows 恒为空、所有层不可行。已修复为直接读 `row["accuracy"]`，并补齐分层断言。
2. **SUGGESTION**：测试夹具 medium 层 solved=5 > total=4 数据不自洽，已修正为 2/4 并同步断言。

## 遗留说明

- issue 第 4 节"成本敏感策略选择器 + 运行中预算降级"按确认拆分为后续独立 change（#56b），本 change 未触碰执行路径。
- 工作区存在未跟踪的 `data/leetcode_demo.json`（会话演示产物，不属于本 change，未纳入提交）。

## 结论

无 CRITICAL/IMPORTANT 遗留问题；全量测试与 OpenSpec 校验通过，可进入归档确认。
