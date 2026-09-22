# Design: 增强的错误分析

## 实现说明

### 分类器（src/error_analysis.py）

- 入口 `classify_failure(result: dict) -> str`：优先级为
  1. 沙箱终态映射：`timeout` → timeout_error；`memory_error` → memory_error；`syntax_error` → syntax_error；`runtime_error` → runtime_error。
  2. `failure_category == "model_error"` 或迭代含 `llm_error` → api_error。
  3. `wrong_answer` / `AssertionError` / 输出不匹配 → logic_error。
  4. 消息正则：`SyntaxError|IndentationError` → syntax_error；`IndexError|KeyError|TypeError|AttributeError|ValueError|NameError|ZeroDivisionError` → runtime_error；`MemoryError` → memory_error；`timed out|timeout` → timeout_error。
  5. 其余 → unknown。
- 输入取自 ExecutionResult 字典：`failure_category`、`error_message`、`final_result.status`、`final_result.test_results[].error_message`、`iterations[].llm_error/sandbox_error`。`budget_exhausted`/`unsupported` 不是错误，不参与分类计数。

### 模式聚合与分布

- `normalize_message(msg)`：取首行、去掉路径前缀、数字替换为 `N`、截断到 120 字符。
- Top 模式：`Counter[normalized].most_common(top_n)`（默认 10）。
- 分布：类别 × 难度（result.difficulty）、类别 × 标签（problem_info 映射，与 experiment_report 相同方式），每格 `{count, share}`。

### 修复建议

- `SUGGESTIONS`：按类别 + 已知异常名二级映射（IndexError/KeyError/TypeError/AttributeError/超时/内存/逻辑）；每类 1–3 条中文建议；unknown 只给"查看完整轨迹与失败输入"通用提示。

### 集成

- `analyze_results(results, problem_info, top_n=10) -> dict`：`{total_failures, categories: {七类: count}, top_patterns: [...], by_difficulty, by_tags, suggestions: {类别: [...]}}`。
- `experiment_report.generate_comparison_report`：每个组合追加 `error_analysis`；整体聚合（全部组合求和）写入 `comparison.json` 的 `error_analysis` 段；REPORT.md 新增章节。
- `experiment_panel._build_panel_data`：新增 `error_categories`（整体类别计数）→ panel.html 渲染 doughnut 图。

### 边界（对 issue 工作范围的一处收敛）

- issue 提到"错误趋势折线图（跨实验对比）"：跨实验趋势需要扫描多个实验目录的聚合索引，当前不存在该索引，本次以"组合间/模型间错误分布对比"替代，跨实验趋势列为后续扩展（适合随 #17 API 一起做）。该收敛已在 proposal 向用户说明。

### 测试策略

- 分类器：7 类各有直接用例（沙箱终态、异常名、消息正则、llm_error、unknown）。
- 模式聚合：仅数字不同的两条消息聚合为 1。
- 分布与建议：手算小夹具断言计数与占比；unknown 不给虚构建议。
- 集成：pairwise 夹具跑通后 comparison.json 含 error_analysis 且计数和=失败数；panel.html 含 doughnut。
