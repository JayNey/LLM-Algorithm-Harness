# 验证报告：model-comparison-panel

- 日期：2026-09-21
- 分支：`tweak/20260921/model-comparison-panel`（基于 upstream/main `a99d8ae`，含已合并的 #46/#44）
- 验证模式：full（1 个 delta spec 能力、17 个任务）
- review_mode：off（tweak 预设默认；以任务级检查 + 全量测试 + 手算对账夹具作为集成验证手段，未安排独立审查者）

## Summary

| 维度 | 状态 |
|------|------|
| Completeness | 17/17 任务完成；delta spec 5 个需求 10 个场景全部有实现与测试 |
| Correctness | 胜率矩阵/显著性/成本效益全部按手算夹具对账通过 |
| Coherence | 实现与 design.md 一致；对既有 comparison 数据结构只增不改（`model_comparison` 新段） |

## 检查项结果

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部勾选 | PASS | 入口状态 17/17 |
| 2 | 实现符合 design.md | PASS | 矩阵/显著性在 `src/experiment_report.py`，面板独立为 `src/experiment_panel.py`，并行在 `src/experiment.py`（组合粒度），与设计一致 |
| 3 | OpenSpec 校验 | PASS | `openspec validate` → valid |
| 4 | 能力规格场景通过 | PASS | 见下方场景清单；全量 457 passed, 4 skipped |
| 5 | proposal.md 目标满足 | PASS | 胜率矩阵、显著性、成本效益、panel.html、并行执行、文档全部落地 |
| 6 | delta spec 与 design 无矛盾 | PASS | 无 Implementation Divergence |
| 7 | 关联设计文档可定位 | N/A | tweak 流程无 docs/superpowers/specs 设计文档 |
| 8 | Runtime 构建/测试证据 | PASS | `comet check run build` exit=0（431276b1） |

## Spec 场景覆盖清单

| 场景 | 测试证据 |
|------|----------|
| 胜率矩阵计算正确（8 题：胜3平4负1） | `test_win_rate_matrix_hand_computed`（分母=总数断言） |
| 预算未完成题参与配对 | `test_budget_exhausted_pairing_counts_as_loss` |
| 差异显著时标注（p=0.03125 < 0.05） | `test_mcnemar_annotation_branches` |
| 样本不足时明确标注 | `test_mcnemar_annotation_branches`（不一致对=0 → "样本不足"） |
| 成本已知模型参与排名 | `test_win_rate_matrix_hand_computed`（model-a 入排名） |
| 成本未知模型不参与排名 | 同上（model-b 进 cost_unknown_models） |
| 面板包含图表与矩阵 | `test_panel_html_contains_charts_and_matrix`（三 canvas + CDN + 矩阵表） |
| 成本未知不进入散点图 | 同上（scatter payload 仅 model-a） |
| 并行执行结果与串行一致 | `test_parallel_execution_matches_serial_structure`（组合顺序/面板/comparison 结构一致） |
| 并行度受配置约束 | `min(max_workers, jobs)` 实现 + max_workers=1 场景通过；未做并发数仪表断言（说明：以结构一致性与上限字段校验覆盖） |

## 手算对账

- 夹具：8 题，model-a 解出 1–6，model-b 解出 1/2/3/7 → A 对 B 胜 3（4/5/6）、负 1（7）、平 4（1/2/3 同过 + 8 同挂），分母 8 ✓。
- 显著性：不一致对 (3,1)，精确二项双侧 p=0.625 不显著；(6,0) → p=0.03125 显著；(0,0) → 样本不足 ✓。
- 成本：model-a 每次调用成本 0.00002（手算 10×0.001/1000 + 5×0.002/1000），8 次调用合计 0.00016，比 6/0.00016=37500 解出/美元；model-b 无定价 → "未知" 排除 ✓。

## 遗留说明

- 面板图表依赖 CDN；离线打开时显示降级提示，表格数据不受影响（已在面板中实现并测试）。
- 并行执行采用组合粒度（每组合独立 harness + BudgetTracker），未使用 TaskService 的按题并行——原因：BudgetTracker 的"当前题"状态与 worker 池互斥；该偏差已在 proposal/design 记录，issue 验收标准未要求 TaskService。
- 工作区存在未跟踪的 `data/leetcode_demo.json`（会话演示产物，不属于本 change，未纳入提交）。

## 结论

无 CRITICAL/IMPORTANT 问题；全量测试与 OpenSpec 校验通过，可进入归档确认。
