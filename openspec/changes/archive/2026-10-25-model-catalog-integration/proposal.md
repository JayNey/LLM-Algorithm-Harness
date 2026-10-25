## Why
监控离线示例与密钥动态模型缺少一致来源说明，容易把示例误认为账户可用模型。

## What Changes
- 扩展现有 GET /api/v1/config/providers，可选 api_key_id 查询本人密钥。
- 静态与动态结果明确标记来源，保留现有字段和鉴权。
- 复用评测模型服务的分页、限流、超时、归属、变更检测和脱敏。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/system-config`: 配置查询明确区分模型目录来源。

## Impact
监控路由、目录元数据、评测响应模型、接口说明与测试；无新路由、数据库迁移或依赖。
