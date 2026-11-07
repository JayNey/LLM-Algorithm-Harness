## 背景

`src/reporting/chart_generator.py`（565 行）的 `generate_token_chart` 对每个迭代的 prompt/completion tokens 用自带 `MODEL_PRICING`/`_calculate_cost` 重算费用；历史费用的权威通道在 `harness._estimate_cost`（逐 trace 累加 `pricing_metadata.total_cost`，reflection 定价已由 `strategy_base._merge_pricing_metadata` 合并进 trace），trace 顶层 token 数也已含 reflection 轮。`_calculate_cost`/`MODEL_PRICING` 无其他使用方；`generate_token_chart` 的唯一生产调用方是 `html_generator`（报告入口），其余为测试。既有测试 `test_chart_generator.py` 多为 metrics-only 调用（正是 70/30 伪造路径），需要按新契约更新。

## 目标与非目标

**目标：** 图表费用/用量直读 trace 已知值；未知如实标注；删除死定价表与 70/30 分支；与文字报告可对账。
**非目标：** 不改 `harness._estimate_cost`、中央定价服务、Markdown/CSV 报告；不引入新依赖；不改变图表的双轴结构与图例样式（仅费用来源与标注变化）。

## 关键决策

- **聚合口径**：每结果 token = Σ trace `total_tokens`（主调用+reflection，与 harness 的 total_tokens 同源）；每结果已知费用 = Σ trace `pricing_metadata.total_cost`（`total_cost` 非 null 且 `usage_known` 非 False）；每策略绘制已知费用的平均值（沿用既有 Average 语义）；percentiles 从每结果 trace token 数计算。
- **未知表达**：已知数 < 结果数时在成本轴注明 "N result(s) with unknown cost excluded from $ axis"（图表标签沿用英文惯例）；全部未知或无结果时不画成本线，`ax2` 留空并在图上说明 "No known cost data"。
- **删除死代码**：`MODEL_PRICING`、`_calculate_cost` 整体删除；`model` 参数随之无用，从 `generate_token_chart` 签名移除并同步唯一调用方 `html_generator`（`model_name` 变量删除）。
- **70/30 分支删除**：metrics-only 或全零场景不再伪造美元值。
- **对账语义**：单结果场景图表费用 == 该结果 trace 已知费用合计 == 文字报告 `estimated_cost_usd` 的组成部分（harness 为 Σ，图表为均值；均值 × 结果数 == Σ，可对账）。

## 风险与取舍

- **[风险]** metrics-only 调用方（测试）失去成本线。**取舍：** 伪造金额正是缺陷；测试按新契约更新。
- **[风险]** 旧结果无 `llm_traces`（更早的历史数据）→ 无已知费用 → 成本轴空。**取舍：** 如实展示优于错误金额；token 轴不受影响。

## 验证

- 新契约测试：历史 $9/$0 直读（复刻 issue repro 的 `_fig_to_bytes` 捕获手法读费用轴）、混合已知/未知标注、reflection 合并费用与 token、无 trace/无已知费用的诚实语义、`MODEL_PRICING` 删除后无残留引用。
- 定向回归 `tests/reporting tests/test_error_handling.py`；全量 `pytest -m "not online" -q --cov-fail-under=0`（覆盖率 ≥90 不稀释）；`ruff check .`、`black --check .`、`git diff --check`；mypy（CI 锁定版本为准，本机 3.12 venv 复核改动文件）。
- 记录到 `docs/superpowers/reports/`。
