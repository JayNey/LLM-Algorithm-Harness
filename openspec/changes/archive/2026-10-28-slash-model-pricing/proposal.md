## Why

Issue #297：定价路由仅匹配单段模型名，含斜杠的真实模型 ID 在 URL 解码后返回 404，无法保存与追溯定价。

## What Changes

- 扩展既有定价路由的路径匹配，接受完整模型 ID，保留普通模型地址、认证和价格及长度校验。
- 前端沿用一次 encodeURIComponent 编码，补充真实 HTTP 与前端契约回归测试。
- 补充接口编码说明与示例。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/cost-management`：定价保存、目录和历史精确保留含斜杠及百分号的模型 ID。

## Impact

修改既有成本 API 路由、定价客户端及相关测试和文档；无新端点、数据库变更或依赖。用户选择独立分支 codex/slash-model-pricing，按单一 tweak change 修复已有契约。
