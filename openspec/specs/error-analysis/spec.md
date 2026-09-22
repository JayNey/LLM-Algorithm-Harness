# error-analysis Specification

## Purpose
对失败结果做系统化错误分析：将错误细分为 7 类、聚合高频错误模式、按难度与标签分布，并给出规则化修复建议，帮助快速定位模型弱点。

## Requirements

### Requirement: 七类错误自动分类

系统 SHALL 依据沙箱终态、异常类型与错误消息把每个失败归入 syntax_error、logic_error、runtime_error、timeout_error、memory_error、api_error、unknown 七类之一；既有粗粒度 `failure_category` 口径保持不变。

#### Scenario: 沙箱终态直接映射

- **WHEN** 沙箱终态为 timeout、memory_error 或 syntax_error
- **THEN** 分别归类为 timeout_error、memory_error、syntax_error，不再依赖消息文本

#### Scenario: 异常类型与消息推断

- **WHEN** 测试错误消息包含 `IndexError`、`KeyError`、`TypeError`、`AttributeError` 等运行时异常名
- **THEN** 归类为 runtime_error；`AssertionError` 或纯输出不匹配归类为 logic_error；LLM 调用失败（model_error 轨迹）归类为 api_error；无法识别归为 unknown

### Requirement: 高频错误模式识别

系统 SHALL 对错误消息做归一化聚合（首行、数字替换为 N），输出出现频率最高的前 N 个模式，并统计错误类别 × 难度、类别 × 标签的分布。

#### Scenario: 相似错误聚合为同一模式

- **WHEN** 两条错误消息仅数字不同（如 `list index out of range: 3` 与 `: 7`）
- **THEN** 聚合为同一模式并计数 2

#### Scenario: 分布带分母

- **WHEN** 生成类别 × 难度或类别 × 标签分布
- **THEN** 每个分组同时给出计数与该分组内占比

### Requirement: 规则化修复建议

系统 SHALL 按错误类别与异常类型给出规则化修复建议；建议仅为提示，不自动修改代码。

#### Scenario: 常见错误给出对应建议

- **WHEN** 失败归类为 runtime_error 且消息含 `IndexError`
- **THEN** 建议包含列表边界检查提示；timeout_error 建议包含复杂度优化提示；logic_error 建议包含边界条件与样例对拍提示

#### Scenario: 未知错误不给虚构建议

- **WHEN** 失败归类为 unknown
- **THEN** 建议为通用的"查看完整轨迹"提示，不虚构具体修法

### Requirement: 实验报告与面板集成

实验对比产物 SHALL 包含 `error_analysis` 段（按组合的错误类别计数、Top 模式、类别 × 难度/标签分布、建议），`REPORT.md` 新增错误分析章节，`panel.html` 新增错误类别占比图。

#### Scenario: comparison.json 包含错误分析

- **WHEN** 实验完成并生成 comparison.json
- **THEN** 每个组合与整体聚合均可查到七类计数、Top 模式与分布，且类别计数之和等于失败题数

#### Scenario: 面板呈现类别占比

- **WHEN** 面板生成
- **THEN** panel.html 含错误类别占比图（Chart.js doughnut）的数据与渲染代码
