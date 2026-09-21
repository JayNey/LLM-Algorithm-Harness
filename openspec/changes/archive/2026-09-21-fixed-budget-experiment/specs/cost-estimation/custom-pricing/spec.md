# cost-estimation/custom-pricing Delta

## MODIFIED Requirements

### Requirement: 未知模型的降级处理

系统 SHALL 在遇到无可用定价的模型时显式标记"定价未知"并记录警告日志，不得使用默认定价折算成本。

#### Scenario: 未知模型使用默认定价

- **WHEN** 模型在 `pricing.json` 和内置字典中均不存在
- **THEN** 系统不再使用默认定价折算：该模型的定价标记为未知并记录警告，成本显示"未知"而不是按默认单价折算的金额

#### Scenario: 结果文件保留未知标记

- **WHEN** 保存 `pricing_metadata`
- **THEN** 未知定价模型的记录包含显式的未知标记，报告中成本显示"未知"而不是 $0

#### Scenario: 警告日志包含模型名称

- **WHEN** 使用未知定价标记
- **THEN** 警告日志包含未知模型的名称
