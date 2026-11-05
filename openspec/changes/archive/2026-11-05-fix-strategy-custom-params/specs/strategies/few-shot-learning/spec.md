## MODIFIED Requirements

### Requirement: 策略必须支持可配置的检索参数

系统 SHALL 允许用户配置示例数量、相似度阈值和相似度计算方式。

#### Scenario: 配置示例数量
- **WHEN** 用户配置 num_examples=5
- **THEN** 系统最多返回 5 个相似题目作为示例

#### Scenario: 配置相似度阈值
- **WHEN** 用户配置 min_similarity_score=0.5
- **THEN** 系统只返回相似度 >= 0.5 的题目

#### Scenario: 使用默认配置
- **WHEN** 用户未提供配置参数
- **THEN** 系统使用默认值：num_examples=3, min_similarity_score=0.3, similarity_metric="tag_overlap"

#### Scenario: 检索控制参数与模型生成参数分离
- **WHEN** 用户同时配置 num_examples、similarity_metric、min_similarity_score、example_source 和合法的模型生成扩展
- **THEN** 检索配置仍实际生效，模型请求只包含生成参数，内部控制键不进入 SDK 或 HTTP 请求
- **AND** 合法扩展保持原有覆盖优先级并参与缓存键，控制参数本身不改变相同 prompt 的模型缓存键
