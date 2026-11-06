# token-chart-historical-cost 验证报告

## 状态
PASS。verify 第 1 轮独立审查 REQUEST_CHANGES（2 项 IMPORTANT + 4 项 WARNING/SUGGESTION），按 verify-fail（第 1 次）回 build 修复并全量重验；第 2 轮定点复审 APPROVE（见文末）。6/6 tasks；delta spec `reporting/token-cost-estimation` 1 项 MODIFIED requirement（8 场景）+ 2 项 REMOVED requirement。归档须等待用户最终确认。

## 范围与规格对照
Issue #368（S16，shouldfix）；分支 `tweak/20261106/token-chart-historical-cost`，基点 `upstream/main@5698e5d`。认领留言见 issue 评论。

| 验收项（issue 修复方向） | 实现 | 回归 |
| --- | --- | --- |
| 复用历史已知费用及统一用量口径 | `generate_token_chart` 聚合直读 `llm_traces`：每结果 token=Σ trace `total_tokens`（主调用+reflection 已合并）、已知费用=Σ `pricing_metadata.total_cost`（非 null 且 `usage_known` 非 False） | 维护者原版复现脚本（适配签名）：历史 $9/$0 → 图表 $9.0/$0.0 |
| 已知 $9、零价 $0 保留；未知明确未知不画伪造美元值 | 未知（缺 metadata/total_cost null/usage_known False）不计入美元轴，标题标注 "N call(s) with unknown cost excluded"；无已知费用时不画成本线并标注 "no known cost data" | `test_known_historical_cost_is_used_directly`、`test_known_zero_cost_stays_zero`、`test_unknown_calls_excluded_and_annotated`、`test_no_known_cost_data_draws_no_dollars`、`test_metrics_only_draws_no_dollars` |
| reflection/reasoning 等已记录消耗统一口径 | trace 顶层 token 已由 `strategy_base._build_llm_traces` 合并主调用+reflection；`pricing_metadata` 已由 `_merge_pricing_metadata` 合并双方已知费用——图表直读该合并值，不漏计不重复计 | `test_reflection_usage_included_via_merged_traces`（误差棒 y=206.25/288.75 来自 trace 口径 165/330，未合并口径会是 150/300 → 187.5/262.5，可区分） |
| HTML 文字、图表及结果 trace 可对账 | 图表费用与 `harness._estimate_cost` 同源（同为 trace 已知费用聚合）；单结果场景 图表均值==结果费用 | 原版复现 + `test_known_historical_cost_is_used_directly` |

**范围扩展（经确认）**：issue 只要求费用来源修复；实施中发现独立定价表 `MODEL_PRICING`/`_calculate_cost` 修复后成为死代码（无任何使用方），按"不用另一套 default 重算"的验收精神整体删除，delta spec 以 REMOVED requirement 记录（系统定价权威在中央定价服务 S04/#359）。`model` 参数随之移除（唯一调用方 `html_generator` 同步；维护者原版复现脚本需去掉 `model=` 实参，PR 中注明）。

## 提交
`d4b9eef` 转义主修复 → `20d340f` 复审修复（NaN 缺口、无 trace 回退、API 合成 trace、token 标签独立、新增 3 组契约用例）。提交信息沿用英文正文（与本分支首提交一致）。

## 验证证据（最终代码状态）
- TDD：issue 自带的 `_fig_to_bytes` 捕获复现为 RED 依据（修复前 $9/$0 均渲染 $0.04），实现后 GREEN。
- 定向：`tests/reporting tests/test_error_handling.py` → **116 passed**（新增 9 项契约/回归测试）。
- 全量（最终态 `20d340f`）：3944 passed、32 skipped、0 failed，覆盖率 93.06%。4 个 ERROR 为本机 httpx/httpx2 SDK 环境问题（tests/test_strategy_provider_params.py，未触碰区域，CI 的 pinned 依赖为准）。
- `ruff check .`、`black --check .`、`git diff --check`：通过。
- mypy：CI 锁定版本为准；本机 3.12 venv 复核改动文件 0 错误（1 条 unused-ignore 提示位于**未触碰**的既有行，main 上即存在且 CI 接受）。
- 既有测试：`test_format_chart_error_special_characters` 等 html_generator 契约测试全部通过（#353 的转义行为不受影响——图表直读 trace 与转义正交）。

## 验证边界与契约记录
- `generate_token_chart` 移除 `model` 参数：图表不再做任何基于 token 的费用估算，模型定价权威在中央定价服务（S04/#359 最长前缀匹配）。维护者审计脚本如需复跑，去掉 `model=` 实参即可。
- metrics-only 调用（无 results）不再产出费用线——70/30 估算按验收要求移除；token 轴不受影响。
- 报告不验证浏览器端实际渲染（matplotlib figure 数据由测试直接断言）。

## 审查与限制（两轮独立审查）
**第 1 轮（`d4b9eef`）**：REQUEST_CHANGES。2 项 IMPORTANT——① 全图布尔 plot_cost 使全部调用未知的策略被画成已知 $0.0000（与已知 $0 无法区分，违反验收项）；② API 报告路径 `_execution_result` 不带 llm_traces，下载 HTML 的图表永远显示 "(no known cost data)" 而文字报告显示 $9——"可对账"验收在该路径失败（审查者以真实 HTMLGenerator.generate 与 API 适配探针实证）。4 项 WARNING——token 标签随 avg_costs 为空消失、无 trace 结果（budget_exhausted 等）从聚合中消失、卡片总额与图表每题均值口径未说明、delta spec 未移除 70/30 需求。

**修复（`20d340f`，verify-fail 第 1 次）**：无已知成本的策略在成本轴留 NaN 缺口（matplotlib 断线，不画 $0）；无 trace 结果按记录的 total_tokens 计入用量轴并计为未知单元；API 路径以存储的 cost_usd/cost_unknown 合成单位级 trace（与 `_known_cost` 规则一致）；token 标签独立于成本项绘制；delta spec 补 REMOVED "成本计算考虑输入输出比例"；轴标签改为 "Known Cost (USD)" 且对账场景按"每题均值 × 结果数 == 合计"表述。SUGGESTION 的 usage_known=False 变异测试、多策略/无 trace 混合用例、报告计数修正均已落实。

**第 2 轮（`git show 20d340f`）**：APPROVE——两项 IMPORTANT 确认解决（端到端复验：A 已知 $9 / B 全部未知 / C 无 trace 的探针输出 [9→9, B→NaN 缺口+标注, C→计入用量并标注]；API 路径 $9/$0 正确呈现），无新发现。遗留：维护者审计脚本需去掉 model= 实参（PR 注明）；secrets.py 贪婪键缺口与本报告既有记录无关。

## 最终状态重验（`20d340f`）
- 定向：`tests/reporting tests/test_error_handling.py` → 116 passed；全量：3944 passed、32 skipped、0 failed、覆盖率 93.06%（4 个 ERROR 为本机 httpx/httpx2 环境问题，见上）。
- `ruff check .`、`black --check .`、`git diff --check`：通过；mypy（3.12 venv）改动文件 0 错误。
- Runtime verify 检查：全量（`-m "not online" -q`，无覆盖率写盘）exit=0；定向/lint 类 exit=0。
- issue 原版复现（适配签名）：历史 $9 → 图表 $9.0；$0 → $0.0（修复前均为 $0.04）。

## 交付策略
上游 PR 只含 2 个源码提交；OpenSpec 归档与验证报告留在本地归档提交（同 #353/#357 惯例）。
