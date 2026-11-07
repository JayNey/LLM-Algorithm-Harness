## 1. 图表聚合重写

- [x] 1.1 `generate_token_chart` 费用/用量改为直读 `llm_traces`：每结果 token=Σ trace `total_tokens`、已知费用=Σ 各 trace `pricing_metadata.total_cost`（非 null 且 `usage_known` 非 False），统计未知单元数并绘图标注；删除 `_calculate_cost`/`MODEL_PRICING`/70-30 估算分支与 `model` 参数，同步 `html_generator` 调用点。 <!-- comet-task:93ca22dc-593e-4049-a57b-ec49bb1574bc -->
- [x] 1.2 无任何已知费用时不绘制成本曲线并明确说明；混合场景美元值只含已知部分。 <!-- comet-task:e7ade6f5-60b9-47bd-9b77-7dc6fc370f09 -->

## 2. 契约测试

- [x] 2.1 按 issue 复现手法（patch `_fig_to_bytes` 读费用轴）断言历史 $9/$0 直读、混合已知/未知标注、reflection 合并费用与 token 口径、无 trace/无已知费用语义、metrics-only 不再伪造美元值。 <!-- comet-task:11c6e687-2d53-4fa2-98fa-b7ce833e1536 -->
- [x] 2.2 更新既有 metrics-only 用例到新契约；确认全仓无 `MODEL_PRICING`/`_calculate_cost` 残留引用。 <!-- comet-task:b370f00f-bf17-4d66-8349-05b0953fc29d -->

## 3. 回归与验证

- [x] 3.1 定向 `pytest tests/reporting tests/test_error_handling.py -q --no-cov`；全量 `pytest -m "not online" -q --cov-fail-under=0`（覆盖率 ≥90 不稀释）；`ruff check .`、`black --check .`、`git diff --check`；mypy 复核改动文件；记录到 `docs/superpowers/reports/`。 <!-- comet-task:d87ea62d-2665-4544-8cf4-f76aaf484cbc -->
