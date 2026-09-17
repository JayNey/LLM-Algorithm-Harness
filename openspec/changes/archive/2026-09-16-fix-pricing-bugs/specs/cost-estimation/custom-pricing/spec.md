## MODIFIED Requirements

### Requirement: 评测时保存定价信息到结果文件

系统 SHALL 在评测运行时将使用的模型定价信息保存到 `summary.json` 中。

#### Scenario: 保存定价元数据到 summary.json
- **WHEN** 评测完成并生成 summary.json
- **THEN** summary.json 包含 `pricing_metadata` 字段，记录每个策略使用的模型定价和来源

#### Scenario: 定价元数据包含必需字段
- **WHEN** 保存定价元数据
- **THEN** 元数据包含 `model`、`prompt_price_per_1k`、`completion_price_per_1k`、`source` 和 `total_cost` 字段

#### Scenario: trace 中的 token 计数位于顶层
- **WHEN** 从 trace 读取 token 计数
- **THEN** 系统从 trace 顶层读取 `prompt_tokens` 和 `completion_tokens`，而非从嵌套的 `pricing_metadata` 读取

#### Scenario: 定价来源标识
- **WHEN** 定价从 `pricing.json` 加载
- **THEN** `source` 字段值为 `custom`
- **WHEN** 定价从内置字典加载
- **THEN** `source` 字段值为 `builtin`
- **WHEN** 使用默认定价
- **THEN** `source` 字段值为 `default`

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

#### Scenario: 前缀匹配使用最长匹配优先
- **WHEN** 定价文件包含 `gpt-4` 和 `gpt-4o` 两个键，且用户请求 `gpt-4o-mini`
- **THEN** 系统匹配 `gpt-4o` 而非 `gpt-4`

#### Scenario: 前缀匹配在无精确匹配时生效
- **WHEN** 定价文件不包含精确的 `gpt-4-0613` 键，但包含 `gpt-4` 前缀
- **THEN** 系统使用 `gpt-4` 的定价
