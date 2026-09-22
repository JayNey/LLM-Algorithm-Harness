# Tasks: 增强的错误分析

## Task 1: 分类器与建议映射

**文件**: 新增 `src/error_analysis.py`

- [x] `classify_failure`：沙箱终态 → api_error → logic_error → 消息正则 → unknown 的优先级分类
- [x] `SUGGESTIONS` 规则映射（含 IndexError/KeyError/超时/内存/逻辑等）；unknown 只给通用提示
- [x] 单元测试：7 类各至少 1 个直接用例；unknown 不给虚构建议

## Task 2: 模式聚合与分布

**文件**: `src/error_analysis.py`

- [x] `normalize_message`（首行、去路径、数字→N、截断）与 Top N 模式计数
- [x] 类别 × 难度、类别 × 标签分布（计数 + 占比）
- [x] `analyze_results` 汇总入口（计数和 = 失败数）
- [x] 测试：数字差异消息聚合为 1；分布占比手算对账

## Task 3: 报告与面板集成

**文件**: `src/experiment_report.py`, `src/experiment_panel.py`

- [x] comparison.json 每组合 + 整体聚合的 `error_analysis` 段；REPORT.md 错误分析章节
- [x] panel.html 错误类别 doughnut 图
- [x] 测试：pairwise 夹具集成断言；panel 含占比图

## Task 4: 文档与回归

**文件**: `docs/experiments.md`

- [ ] 错误分类规则、建议口径与面板使用说明
- [ ] 全量测试 + OpenSpec validate 通过
