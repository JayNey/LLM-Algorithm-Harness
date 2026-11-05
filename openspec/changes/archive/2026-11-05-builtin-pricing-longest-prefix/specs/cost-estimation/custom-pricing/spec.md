## MODIFIED Requirements

### Requirement: 支持从配置文件加载自定义定价

系统 SHALL 支持从项目根目录的 `pricing.json` 文件读取模型定价配置。自定义与内置定价 SHALL 均先精确匹配，再按最长前缀匹配，结果不得依赖字典插入顺序；来源优先级 SHALL 为精确 Web override、自定义、内置、未知。

#### Scenario: 配置文件存在时加载自定义定价
- **WHEN** `pricing.json` 文件存在且格式有效
- **THEN** 系统使用配置文件中的定价数据进行成本估算

#### Scenario: 配置文件不存在时回退到内置定价
- **WHEN** `pricing.json` 文件不存在
- **THEN** 系统使用内置定价字典进行成本估算

#### Scenario: 配置文件格式无效时回退并记录警告
- **WHEN** `pricing.json` 文件存在但 JSON 格式无效
- **THEN** 系统记录警告日志并回退到内置定价字典

#### Scenario: 前缀匹配使用最长匹配优先
- **WHEN** 定价文件包含 `gpt-4` 和 `gpt-4o` 两个键，且用户请求 `gpt-4o-mini`
- **THEN** 系统匹配 `gpt-4o` 而非 `gpt-4`

#### Scenario: 前缀匹配在无精确匹配时生效
- **WHEN** 定价文件不包含精确的 `gpt-4-0613` 键，但包含 `gpt-4` 前缀
- **THEN** 系统使用 `gpt-4` 的定价

#### Scenario: 内置日期模型选择最具体模型族
- **WHEN** 无自定义及覆盖价格，查询 `gpt-4o-2024-08-06` 或 `gpt-4-turbo-2024-04-09`
- **THEN** 分别使用 `gpt-4o` 的 (0.005, 0.015) 和 `gpt-4-turbo` 的 (0.01, 0.03) 单价（USD/1k tokens），不受插入顺序影响

#### Scenario: 响应费用参与预算判断
- **WHEN** 日期模型响应返回已知 token 用量
- **THEN** 响应定价元数据、累计费用和预算判断使用最具体模型族单价计算的费用
