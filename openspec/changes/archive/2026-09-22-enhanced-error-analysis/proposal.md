# Proposal: 增强的错误分析

## Why

现有失败记录只有粗粒度的 `failure_category`（wrong_answer/system_error 等）和错误消息，无法回答"模型主要犯哪类错、哪类题上犯、怎么改"。issue #52 要求系统化的错误分析：细分错误分类、高频模式、规则化修复建议，并纳入实验对比报告。前置 #13 已完整保存每轮轨迹与失败用例，数据齐备。

## What Changes

- 新增 `src/error_analysis.py`：
  - **7 类错误分类器**：`classify_error` 依据沙箱终态、异常类型与错误消息，输出 syntax_error / logic_error / runtime_error / timeout_error / memory_error / api_error / unknown；现有粗粒度 `failure_category` 保持不变（分类器是对 system_error/wrong_answer 的细化，不改变既有口径）。
  - **高频模式识别**：错误消息按首行 + 数字归一化聚合，输出 Top N 高频模式；统计错误类别 × 难度、类别 × 标签分布。
  - **修复建议映射**：按异常类型/类别给出规则化中文修复建议（如 IndexError → 检查边界；KeyError → 使用 .get()；超时 → 优化复杂度）；不做 LLM 建议、不自动修复（遵循 issue 边界）。
- 实验报告集成（`src/experiment_report.py`）：`comparison.json` 新增 `error_analysis` 段（按组合的错误类别计数、Top 模式、类别×难度/标签分布）；`REPORT.md` 新增"错误分析"章节（类别分布、Top 10 模式、修复建议）。
- 交互面板集成（`src/experiment_panel.py`）：`panel.html` 新增错误类别饼图（Chart.js doughnut）。
- 文档：`docs/experiments.md` 补充错误分类规则与建议口径。

## Capabilities

### New Capabilities

- `error-analysis`: 错误自动分类、模式识别与修复建议（新能力，实验报告与面板消费）。

### Modified Capabilities

（无——experiment/budget-comparison 的既有需求不变，仅消费新能力的数据）

## Impact

- 代码：新增 `src/error_analysis.py`；`src/experiment_report.py` 与 `src/experiment_panel.py` 集成；新增 `tests/test_error_analysis.py`。
- 兼容性：只读分析，不改变执行路径与既有结果格式；`comparison.json` 为新增字段。
