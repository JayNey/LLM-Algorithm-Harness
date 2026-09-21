# reporting/token-cost-estimation Specification

## Purpose
基于 token 使用量和模型定价提供成本估算能力，帮助用户评估不同策略的经济效益。

## Requirements

### Requirement: 支持主流模型定价配置

系统 SHALL 支持配置主流 LLM 模型的定价信息，包括每百万 token 的输入和输出价格；无可用定价的模型显式标记为未知，不使用默认定价折算。

#### Scenario: 使用内置定价计算 GPT-4 成本

- **WHEN** 评测使用 gpt-4 模型且未提供自定义定价
- **THEN** 系统使用内置的 GPT-4 定价（输入 $30/M tokens，输出 $60/M tokens）计算成本

#### Scenario: 使用自定义定价

- **WHEN** 用户在配置中提供自定义模型定价
- **THEN** 系统使用用户提供的定价而不是内置默认值

#### Scenario: 未知模型使用默认定价

- **WHEN** 评测使用的模型不在内置定价列表中且未提供自定义定价
- **THEN** 系统不再使用通用默认定价折算：该模型的定价标记为未知，成本显示"未知"而不是虚构的默认金额

### Requirement: Token 图表显示成本信息

Token 消耗图表 SHALL 使用双 Y 轴同时显示 token 数量和对应的成本估算。

#### Scenario: 双 Y 轴显示 tokens 和成本

- **WHEN** 生成 Token 消耗图表
- **THEN** 图表左侧 Y 轴显示平均 token 数量，右侧 Y 轴显示对应的美元成本，两条曲线叠加显示

#### Scenario: 成本曲线使用不同颜色和标记

- **WHEN** 图表同时显示 tokens 和成本
- **THEN** token 数量使用蓝色实线，成本使用绿色虚线，图例清晰标注

### Requirement: 成本计算考虑输入输出比例

成本估算 SHALL 基于实际的输入输出 token 比例，而不是简单使用总 token 数和单一价格。

#### Scenario: 使用输入输出 token 分别计算

- **WHEN** 策略产生 1000 输入 tokens 和 500 输出 tokens
- **THEN** 成本 = (1000 × 输入价格 + 500 × 输出价格) / 1,000,000

#### Scenario: 缺少输入输出分离数据时使用保守估算

- **WHEN** 评测结果只提供总 token 数未区分输入输出
- **THEN** 系统假设 70% 为输入 tokens，30% 为输出 tokens 进行估算

### Requirement: 成本以美元显示并格式化

成本金额 SHALL 以美元货币格式显示，小于 $1 时显示到小数点后 4 位，大于 $1 时显示到小数点后 2 位。

#### Scenario: 小额成本显示精确值

- **WHEN** 单个问题的成本为 $0.00123
- **THEN** 显示为 "$0.0012"

#### Scenario: 大额成本显示常规格式

- **WHEN** 总成本为 $12.3456
- **THEN** 显示为 "$12.35"
