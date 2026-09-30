# Failure Mode Classifier Specification

## ADDED Requirements

### Requirement: 失败结果细分类

系统 MUST 为已完成的失败结果记录独立于 `failure_category` 的 `failure_mode`，至少覆盖语法错误、逻辑错误、超时、边界条件遗漏和题意理解错误，并在证据不足时使用保守的 `unknown`。系统 MUST 记录非敏感规则证据标识和规则置信度。

#### Scenario: 明确的语法失败

- **Given** 已完成结果的沙箱终态是语法错误
- **When** Harness 保存结果
- **Then** `failure_mode` 是 `syntax_error`，证据不包含原始代码或测试输入，原有 `failure_category` 保持原值

#### Scenario: 证据不足

- **Given** 一条 wrong answer 结果没有能区分边界遗漏与题意错误的线索
- **When** 执行细分类
- **Then** 系统不凭空标成 `boundary_condition` 或 `understanding_error`

### Requirement: 非失败结果不分类

系统 MUST 不将成功、预算耗尽、不支持、取消或 `evaluation_completed: false` 的任务占位记录计为已完成的失败。

#### Scenario: 预算暂停留下占位记录

- **Given** 一个结果状态为 `cancelled` 或 `budget_exhausted`
- **When** 分类并聚合运行结果
- **Then** 该结果没有失败模式，也不进入已评估和失败分母

### Requirement: 失败模式报告

系统 MUST 在运行结果中提供按失败模式的数量与占比、按题目标签的失败率和分母，并为非空失败集合生成分布图。弱项排序 MUST 展示样本数并排除少于 3 条已评估记录的标签。

#### Scenario: 多标签题目的失败

- **Given** 一个失败题目同时带有 `graph` 和 `dp` 标签
- **When** 汇总失败模式
- **Then** 总失败数增加一次，两个标签组各增加一次失败，两个标签组各以本组已评估数计算失败率

#### Scenario: 没有失败

- **Given** 所有已评估题目成功
- **When** 生成失败模式报告
- **Then** 报告显示零失败且不生成分布图

### Requirement: 分类准确率验收

系统 MUST 在固定的人工标注案例集上达到严格大于 85% 的分类准确率，案例集 MUST 包含五类主要模式和易混淆样本。

#### Scenario: 离线准确率验证

- **Given** 每条案例有独立标注的预期失败模式
- **When** 在不调用外部模型的条件下运行分类器
- **Then** 正确分类数除以案例总数严格大于 0.85，测试输出案例数量与正确数量
