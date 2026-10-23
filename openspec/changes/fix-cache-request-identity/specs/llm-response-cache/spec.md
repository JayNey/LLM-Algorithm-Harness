## MODIFIED Requirements

### Requirement: 缓存键唯一性
系统 SHALL 为每次 LLM 调用生成唯一的缓存键，基于 provider、有效端点、model、prompt、system_prompt、合并后的生成参数、problem_id 和 strategy_name 的确定性 SHA256 哈希，并使用版本字段隔离旧缓存。超时和重试配置 SHALL 不影响缓存身份。

#### Scenario: 相同参数生成相同缓存键
- **WHEN** 两次调用使用相同端点身份和完整有效生成参数，仅映射键顺序不同
- **THEN** 系统生成相同缓存键并复用缓存

#### Scenario: 任一参数不同生成不同缓存键
- **WHEN** provider、有效端点、提示或任一生成参数（含 thinking、top_p、seed、stop、extra_body、response_format）不同
- **THEN** 系统生成不同缓存键并重新调用 API

#### Scenario: 旧缓存不复用
- **WHEN** 缓存中仅存在未包含完整请求身份的旧版键
- **THEN** 系统将新请求视为缓存未命中
