## Context
监控 providers 读取公开示例；评测模型服务已实现安全枚举。用户选择新分支 comet/model-catalog-integration。

## Goals / Non-Goals
统一现有配置入口的查询与来源，不把静态示例宣称为完整清单，不改变普通用户权限。

## Decisions
- providers 不传 api_key_id 返回静态；传入非空值查询管理员本人密钥，复用已有模型服务。
- 统一 providers 数组。静态 source=static_examples、scope=offline_example_catalog、live_provider_availability_checked=false；动态 source=provider_api、scope=user_api_key、live_provider_availability_checked=true，行内保留 provider/models/complete。
- 评测模型响应增加相同动态 source/scope。枚举成功不保证推理可用。
- 保留脱敏 404/409/429/503，不回退静态示例，不返回密钥 ID 或凭据。

## Risks / Trade-offs
静态示例不完整：保留明确 scope；动态外部请求：沿用 10 秒预算、500 模型上限、禁重试和 no-store。

## 兼容扩展与流程决策
用户已选择继续 tweak：改动虽达 8 个代码、测试和版本文档文件，仍属于单一 change，额外文件用于兼容契约维护，无新增路由或架构协调。独立审查确认前端忽略新增响应字段，可选参数缺省保持原行为。按版本策略更新为 1.1.0，并只定向同步审查过的可选参数与响应属性，不放宽兼容门禁。
