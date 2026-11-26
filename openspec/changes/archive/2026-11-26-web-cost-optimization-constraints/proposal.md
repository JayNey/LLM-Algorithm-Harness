# Web 成本优化约束

## Why

Issue #523：实验详情成本优化页仅传 objective，无法使用现有 CLI/API 的预算与最低准确率能力。客户端还会丢弃 budget_plan 的难度分层信息，导致用户无法查看可行方案与不可行原因。

## What Changes

- 增加可选预算（USD）和最低准确率（百分比）输入；留空沿用现有行为，非法值本地反馈。
- 复用现有客户端和 `/optimize`，按既有语义展示三目标推荐、组合排名、预算汇总与难度分层方案及不可行原因。
- 请求失败可重试，修改约束后旧结果不冒充当前输入结果；保留加载期间可编辑的表单。
- 以固定 comparison 数据核对表单、请求参数、共享 build_advisory 处理与实际结果，无付费模型调用。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/experiments-management`：补充成本优化约束输入、预算结果、校验与请求恢复要求。

## Impact

影响实验详情页、实验客户端及响应类型、中英文文案、相关客户端与浏览器测试和 API 集成回归。复用既有分析算法及 API 契约，不扩展服务地址、密钥或沙箱权限。预计实现与测试约 6–8 个交付文件；实际超出 tweak 的 6 文件提示阈值时按流程提交范围复核。
