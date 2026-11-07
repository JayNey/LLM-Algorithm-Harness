## Why

HTML Token 图表（`ChartGenerator.generate_token_chart`）用自带的硬编码价格表/default 对已保存结果重新计算费用，不复用历史 trace 的定价；漏计 reflection 轮用量；全零费用还会触发 70/30 估算伪造美元值。结果是图表与文字报告（`harness._estimate_cost` 的历史已知费用）对不上账（issue #368，S16，置信度高：历史 $9/$0 均被画成 $0.04）。

## What Changes

- `ChartGenerator.generate_token_chart` 的费用与用量聚合改为直读结果 `llm_traces`：每结果的 token 数取 trace 顶层 `total_tokens` 之和（已含主调用与 reflection 轮），每结果的已知费用取各 trace `pricing_metadata.total_cost`（`total_cost` 非空且 `usage_known` 非 False）之和——与 `harness._estimate_cost` 同一语义，图表与文字报告可对账。
- 未知费用（缺 `pricing_metadata`、`total_cost` 为 null、`usage_known` 为 False）不计入美元值并在图上明确标注数量；无任何已知费用时成本轴不绘制伪造金额，仅保留 token 轴并说明无已知费用。
- 删除图表内独立定价表 `MODEL_PRICING` 与 `_calculate_cost`（修复后无任何使用方；系统定价权威在中央定价服务，S04/#359 已实现最长前缀匹配）。
- 移除"全部为零时 70/30 估算"分支；保留美元格式化与图例结构不变。
- 不改 Markdown/CSV 报告、不改 `harness._estimate_cost` 与中央定价服务。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `reporting/token-cost-estimation`：Token 图表的费用来源改为历史 trace 已知成本（含 reflection 合并口径），未知费用不绘制伪造美元值；图表不再维护独立定价表与 70/30 估算。

## Impact

- `src/reporting/chart_generator.py`（聚合重写、删除死定价表）与 `src/reporting/html_generator.py`（调用点不再传 `model`）、`tests/reporting/test_chart_generator*.py`（新契约测试）。
- 导出 HTML 报告的费用轴与文字报告对账；行为变化即修复目标（此前重算的金额不再出现）。
