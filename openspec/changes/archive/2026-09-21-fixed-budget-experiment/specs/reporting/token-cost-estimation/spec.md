# reporting/token-cost-estimation Delta

## MODIFIED Requirements

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
