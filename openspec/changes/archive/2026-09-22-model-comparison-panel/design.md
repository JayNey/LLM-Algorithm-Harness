# Design: 模型对比分析面板

## 实现说明

### 胜率矩阵与显著性（src/experiment_report.py）

- 从各组合的 `<strategy>_results.json` 组装 `模型×题` 结果矩阵（solved = status=="success"；budget_exhausted 视为未解出）。
- 重复 >1 时按题取多数结果（多数重复解出计为解出），再在模型两两之间配对：A 过 B 挂 = A 胜，同果 = 平。
- 显著性：`scipy.stats` 精确 McNemar / 二项检验，输入为不一致对 (b, c)；`min(b,c) < 1` 或总量过小 → 标注"样本不足"。
- 成本效益：优先用各组合 `pricing_metadata.total_cost` 与已知定价（cost.known）；比 = 完成题的通过数 / 总成本；未知成本排除并标注。

### 数据流

`generate_comparison_report` 聚合组合指标后，新增 `model_comparison` 段写入 `comparison.json`：`{strategy: {matrix: [...], significance: [...], cost_effectiveness: [...]}}`。面板直接消费 comparison.json，不重复计算。

### HTML 面板（新增 src/experiment_panel.py）

- `generate_html_panel(exp_dir)`：读 comparison.json → 渲染 `panel.html`。
- Chart.js 走 CDN（`https://cdn.jsdelivr.net/npm/chart.js`），数据以 `<script type="application/json">` 内嵌；`navigator.onLine` 检测离线时显示降级提示条。
- 图表：雷达图（各模型多维度：隐藏通过率、样例验证率、修复率、成本效益归一化）、散点图（x=成本，y=隐藏通过率，成本未知不进图）、柱状图（平均调用/token/耗时并排）；胜率矩阵渲染为 HTML 表格。
- runner 在生成 comparison.json 后调用 `generate_html_panel`。

### 并行执行（src/experiment.py + src/models.py）

- `ExperimentConfig.execution: Literal["serial","parallel"] = "serial"`；并行度 = `min(max_workers, 组合数)`，max_workers 复用 HarnessConfig 默认（或新增配置字段 `max_workers`，默认 4）。
- 并行实现：`ThreadPoolExecutor` 遍历组合，每个组合独立 AlgorithmHarness + BudgetTracker + 独立落盘目录；组合内串行逻辑与 serial 完全一致。
- 不使用 TaskService 的原因：其 worker 池按题并行，与 BudgetTracker 的"当前题"状态互斥；组合粒度并行达成并行目标且无共享可变状态。此偏差已在 proposal 记录。

### 测试策略

- 胜率矩阵：构造双模型夹具（A 6 过 / B 4 过，交叉 3/1），手算胜平负与分母断言；含 budget_exhausted 配对场景。
- 显著性：构造显著差异夹具断言 p<0.05 标注；全平局断言"样本不足"。
- 成本效益：已知定价排名 + 未知定价排除。
- 并行：同配置 serial vs parallel 组合数据结构一致；并行度上限断言。
- 面板：panel.html 包含三种图表标识与胜率矩阵表格；成本未知模型不出现于散点数据。
