## ADDED Requirements

### Requirement: 模型目录来源与统一查询
系统 SHALL 在现有 GET /api/v1/config/providers 区分静态支持示例与本人密钥动态模型。两类响应 SHALL 返回 providers 数组、source、scope、live_provider_availability_checked。无 api_key_id 时 SHALL 返回 source=static_examples、scope=offline_example_catalog、live_provider_availability_checked=false，只读取公开固定示例，不暗示完整模型支持清单。提供非空 api_key_id 时 SHALL 返回 source=provider_api、scope=user_api_key、live_provider_availability_checked=true，数组只包含该供应商的 provider、models、complete。评测模型接口 SHALL 使用相同动态 source/scope。

#### Scenario: 默认离线查询
- **WHEN** 管理员不传 api_key_id 查询
- **THEN** 返回静态来源，不查询供应商或读取私有运行配置

#### Scenario: 动态查询
- **WHEN** 管理员传入本人有效密钥
- **THEN** 返回动态列表及 complete，来源与评测接口一致，响应 no-store；枚举成功不保证推理可用

#### Scenario: 权限隔离
- **WHEN** 查询他人、已删除、不存在的密钥，或未登录、普通用户访问
- **THEN** 分别返回 404、401、403，不调用供应商

#### Scenario: 失败和截断
- **WHEN** 供应商失败、密钥并发变化、限流或分页截断
- **THEN** 保留脱敏 503、409、429 或 complete=false，不回退静态；沿用既有超时、500 模型上限、客户端关闭

#### Scenario: 空密钥参数
- **WHEN** api_key_id 是空字符串
- **THEN** 返回 400，不静默返回静态目录
