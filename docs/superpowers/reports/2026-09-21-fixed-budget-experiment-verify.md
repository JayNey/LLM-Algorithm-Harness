# 验证报告：fixed-budget-experiment

- 日期：2026-09-21
- 分支：`tweak/20260921/fixed-budget-experiment`（基于 main `30a8f29`）
- 验证模式：full（3 个 delta spec 能力、21 个任务、约 40 个变更文件）
- review_mode：off（tweak 预设默认；以任务级检查 + 全量测试 + 固定夹具手算对账作为集成验证手段，未安排独立审查者）

## Summary

| 维度 | 状态 |
|------|------|
| Completeness | 21/21 任务完成；3 个 delta spec 全部有对应实现与测试 |
| Correctness | 14 个新增需求场景均有实现证据；核心/高风险场景测试通过 |
| Coherence | 实现与 design.md 一致（预算原语独立为 `src/budget.py`，已同步到 tasks.md）；与既有 spec 无矛盾 |

## 检查项结果

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部勾选 | PASS | 入口状态 `taskState.total=21, completed=21` |
| 2 | 实现符合 design.md | PASS | BudgetTracker/BudgetedLLMClient（`src/budget.py`）、`src/experiment.py`、`src/experiment_report.py`、`src/main.py` experiment 子命令与设计一致；模块拆分差异已回写 tasks.md |
| 3 | OpenSpec 校验 | PASS | `comet classic openspec -- validate fixed-budget-experiment` → valid（初次发现 MODIFIED delta 缺场景锚点，已回 build 修复） |
| 4 | 能力规格场景通过 | PASS | 新增 29 个实验/预算/报告测试 + 存量套件全绿（442+ passed） |
| 5 | proposal.md 目标满足 | PASS | 预算实验、可复现元数据、对比报告、未知定价标记、CLI 子命令全部落地 |
| 6 | delta spec 与 design 无矛盾 | PASS | 场景锚点修复后校验通过；design.md 无需 Implementation Divergence 记录 |
| 7 | 关联设计文档可定位 | N/A | tweak 流程无 docs/superpowers/specs 设计文档 |
| 8 | Runtime 构建/测试证据 | PASS | `comet check run build --local -- python3 -m pytest tests/ -q --no-cov` exit=0（26665807） |

## 核心场景验证证据（手算对账）

- 调用数预算：`max_calls=1` 下多轮策略第 1 轮失败后第 2 轮被拒，终态 `budget_exhausted`、失败分类为空、已完成轮次保留（`test_multi_round_stops_on_call_budget_with_completed_rounds`）。
- token 预算：已知用量累计（15+15=30 ≥ 20）触发停止（`test_token_budget_counts_known_usage`）；无 usage + 硬 token 预算 → `token_budget_unsupported`（`test_usage_missing_flags_unsupported_token_budget`）。
- 耗时预算：`max_seconds` 到期后拒绝调用（`test_time_budget_stops_problem`）。
- 分母口径：总数=完成+预算未完成；通过率按总数与按完成双口径（`test_comparison_report_budget_exhausted_and_ranges` 手算 2/0/2）。
- 对比指标：隐藏通过率 1/1、样例验证率 2/2、修复率 2/2、平均调用 1 vs 2、平均 token 15 vs 30，全部与固定夹具手算一致（`test_comparison_report_hand_computed_metrics`）。
- 跨重复：`repeats=2` 输出 min/max 范围与不确定性说明，单次运行输出"单次运行"说明。
- 未知定价：无定价模型成本为 None、汇总标记 `unknown_pricing/unknown_usage`、报告与 CLI 显示"未知"而非 $0；`estimate_cost` 返回 None（`test_estimate_cost_unknown_model`、`test_generate_shows_unknown_cost_for_unknown_pricing`）。
- 可复现元数据：题集 SHA-256 与 git commit 断言；重跑生成新目录不覆盖（`test_runner_rerun_creates_new_directory`）。

## 验证过程中发现并已修复的问题

1. **IMPORTANT**：MODIFIED delta 缺少现行 spec 场景锚点（"未知模型使用默认定价"），`openspec validate` 报错、归档会被拒绝。已回 build 修复：保留场景锚点、改写内容为新行为。
2. **IMPORTANT**：harness 隐藏评测会把带代码的 `budget_exhausted` 终态覆盖为 `failed/wrong_answer`，污染失败分类与分母。已修复：预算未完成的结果跳过隐藏评测（`src/harness.py`）。
3. **SUGGESTION**：`test_runner_rerun_creates_new_directory` 依赖 glob 顺序导致偶发失败。已修复为排序后比较。
4. **顺带发现（已在本 change 内一并修复）**：`pricing.example.json` 的键格式（`prompt_price_per_1k`）与旧加载器（读 `prompt`）不一致，导致自定义定价静默回退内置价。加载器现已兼容两种键格式并支持 `as_of` 日期。

## 遗留说明

- `tests/test_online_verification.py` 在无 `SILICONFLOW_API_KEY` 时跳过（4 skipped），属预期行为。
- 工作区存在未跟踪的 `data/leetcode_demo.json`（会话期间 LeetCode 导入演示产物，不属于本 change，未纳入提交）。

## 结论

无 CRITICAL 问题；2 个验证中发现的 IMPORTANT 问题均已修复并复验。全部检查通过，可以进入归档确认。
