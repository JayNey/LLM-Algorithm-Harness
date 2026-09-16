## Purpose

允许用户通过配置文件自定义 LLM 模型的 Token 定价，评测时将定价保存到结果文件中，报告生成时优先使用历史定价数据以确保成本估算的准确性和一致性。

## ADDED Requirements

### Requirement: 支持从配置文件加载自定义定价

系统 SHALL 支持从项目根目录的 `pricing.json` 文件读取模型定价配置。

#### Scenario: 配置文件存在时加载自定义定价
- **WHEN** `pricing.json` 文件存在且格式有效
- **THEN** 系统使用配置文件中的定价数据进行成本估算

#### Scenario: 配置文件不存在时回退到内置定价
- **WHEN** `pricing.json` 文件不存在
- **THEN** 系统使用内置定价字典进行成本估算

#### Scenario: 配置文件格式无效时回退并记录警告
- **WHEN** `pricing.json` 文件存在但 JSON 格式无效
- **THEN** 系统记录警告日志并回退到内置定价字典

### Requirement: 定价配置文件格式规范

`pricing.json` SHALL 使用以下 JSON 格式：包含顶层 `models` 对象，每个模型键对应一个包含 `prompt` 和 `completion` 定价的对象（单位为美元/1000 tokens）。

#### Scenario: 标准定价配置格式
- **WHEN** 配置文件包含模型名称、prompt 定价和 completion 定价
- **THEN** 系统成功解析并应用该定价

#### Scenario: 支持模型别名和精确匹配
- **WHEN** 配置文件包含模型 `gpt-4` 的定价，且用户使用 `gpt-4-0613`
- **THEN** 系统尝试精确匹配 `gpt-4-0613`，失败后尝试前缀匹配 `gpt-4`

### Requirement: 评测时保存定价信息到结果文件

系统 SHALL 在评测运行时将使用的模型定价信息保存到 `summary.json` 中。

#### Scenario: 保存定价元数据到 summary.json
- **WHEN** 评测完成并生成 summary.json
- **THEN** summary.json 包含 `pricing_metadata` 字段，记录每个策略使用的模型定价和来源

#### Scenario: 定价元数据包含必需字段
- **WHEN** 保存定价元数据
- **THEN** 元数据包含 `model`、`prompt_price_per_1k`、`completion_price_per_1k` 和 `source` 字段

#### Scenario: 定价来源标识
- **WHEN** 定价从 `pricing.json` 加载
- **THEN** `source` 字段值为 `custom`
- **WHEN** 定价从内置字典加载
- **THEN** `source` 字段值为 `builtin`
- **WHEN** 使用默认定价
- **THEN** `source` 字段值为 `default`

### Requirement: 报告生成时优先使用历史定价

系统 SHALL 在生成 HTML 和 Markdown 报告时优先使用 `summary.json` 中保存的定价数据，而不是重新查询当前配置。

#### Scenario: 使用历史定价重新生成报告
- **WHEN** 用户基于已有 summary.json 生成报告
- **THEN** 报告使用 summary.json 中的 `pricing_metadata` 计算成本

#### Scenario: 历史定价缺失时回退到当前配置
- **WHEN** summary.json 不包含 `pricing_metadata` 字段
- **THEN** 系统使用当前定价配置重新估算成本并记录警告

### Requirement: 未知模型的降级处理

系统 SHALL 在遇到未知模型时使用默认定价并记录警告日志。

#### Scenario: 未知模型使用默认定价
- **WHEN** 模型在 `pricing.json` 和内置字典中均不存在
- **THEN** 系统使用默认定价（prompt: $0.002/1k, completion: $0.002/1k）并记录警告

#### Scenario: 警告日志包含模型名称
- **WHEN** 使用默认定价
- **THEN** 警告日志包含未知模型的名称和使用的默认定价值

### Requirement: 报告中显示定价来源

HTML 和 Markdown 报告 SHALL 在成本部分显示定价来源信息。

#### Scenario: 报告显示自定义定价来源
- **WHEN** 成本估算使用 `pricing.json` 的定价
- **THEN** 报告显示 "定价来源: 自定义配置 (pricing.json)"

#### Scenario: 报告显示内置定价来源
- **WHEN** 成本估算使用内置定价字典
- **THEN** 报告显示 "定价来源: 内置定价"

#### Scenario: 报告显示默认定价警告
- **WHEN** 成本估算使用默认定价
- **THEN** 报告显示 "定价来源: 默认值 (模型定价未配置)"
