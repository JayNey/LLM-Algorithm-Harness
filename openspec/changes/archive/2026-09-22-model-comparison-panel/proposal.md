# Proposal: 模型对比分析面板

## Why

issue #15（#46）已交付多模型实验框架：`ExperimentConfig.models` 多模型列表、相同题目集/策略/预算的条件对齐、`comparison.json/csv/REPORT.md`。但 #48 要求的横向对比分析尚缺：模型间胜率矩阵、统计显著性标注、成本效益排名，以及可交互的 HTML 对比面板。模型选型需要这些直接可比的结论，而不是逐组合翻看。

## What Changes

- 对比报告新增**模型胜率矩阵**：同策略下逐题配对（A 过 B 挂 = A 胜，双方同果为平），输出胜/平/负计数与比率，重复实验按题取多数结果后配对。
- 新增**统计显著性标注**：McNemar 检验（scipy 已有依赖）对配对胜负计数给出 p 值与显著性标记，样本量过小时明确标注"样本不足"。
- 新增**成本效益分析**：准确率/成本比排名；成本未知的模型标注"未知"，不参与成本比排名也不显示 $0。
- 新增**交互式 HTML 对比面板**（`panel.html`）：使用 Chart.js（CDN 引入，不自建图表引擎），含雷达图（多维度能力）、散点图（成本 vs 准确率）、柱状图（并排指标），以及胜率矩阵表格；数据以 JSON 内嵌。
- 实验配置新增 `execution: serial | parallel`（默认 serial）：parallel 时按**组合粒度**并行（每个组合独立 harness 与 BudgetTracker，无共享可变状态）；说明：issue 提到"基于 TaskService"，但 TaskService 的 worker 池按题并行会与"当前题"语义的预算追踪冲突，组合粒度并行达成同一目标且安全，串行行为不变。
- 文档更新：`docs/experiments.md` 补充对比面板与胜率/显著性口径，README 同步入口。

## Capabilities

### New Capabilities

（无——全部为既有 `experiment/budget-comparison` 能力的扩展）

### Modified Capabilities

- `experiment/budget-comparison`: ADDED——模型胜率矩阵与显著性、成本效益排名、交互式 HTML 面板、组合粒度并行执行。

## Impact

- 代码：`src/experiment_report.py`（胜率矩阵、显著性、成本效益、面板数据组装）、新增 `src/experiment_panel.py`（HTML 渲染）、`src/experiment.py`（并行执行 + 面板调用）、`src/models.py`（`execution` 配置字段）。
- 测试：胜率矩阵手算对账、显著性标注边界（平局/样本不足/成本未知）、并行执行结果与串行一致、面板 HTML 包含图表与数据。
- 无新增 Python 依赖（Chart.js 走 CDN；scipy 已有）；现有 CLI 与报告行为不变，`panel.html` 为新增产物。
