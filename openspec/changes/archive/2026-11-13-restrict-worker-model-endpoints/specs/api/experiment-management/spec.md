## ADDED Requirements

### Requirement: 实验与 A/B 的模型端点由服务端控制

实验与 A/B 创建接口 SHALL 在保存配置前拒绝任何非 `null` 的模型 `base_url`。Worker SHALL 从用户拥有的 API 密钥及服务端配置解析模型提供商端点。历史任务中的非 `null` 地址覆盖值 SHALL 导致执行失败，Worker SHALL 在初始化 Runner 或发起模型请求前拒绝执行。

#### Scenario: 创建请求包含模型地址

- **WHEN** 登录用户在任一实验模型或 A/B 模型中提交非 `null` 的 `base_url`
- **THEN** 接口返回带字段错误的 400，且无业务配置保存

#### Scenario: 历史任务保存了模型地址

- **WHEN** Worker 领取了历史实验或 A/B 任务，且该任务保存了非 `null` 的 `base_url`
- **THEN** 任务以明确原因失败，且无模型客户端初始化或出站模型请求

#### Scenario: 常规任务使用服务端端点

- **WHEN** 实验或 A/B 模型的 `base_url` 缺省或为 `null`
- **THEN** Worker 继续使用服务端的提供商端点和用户拥有的密钥，并应用模型温度配置
