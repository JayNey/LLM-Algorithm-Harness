# 修复 WebSocket 会话失效后的数据访问

## Why

GitHub issue #510 指出，进度 WebSocket 只在建连时验证访问令牌，此后缓存身份。HTTP 会话注销或令牌到期后，旧连接仍可订阅评估并接收数据，实时通道未遵守认证失效边界。

## What Changes

- 在处理客户端动作、发送评估快照和转发进度事件前重新核验建连时实际使用的凭据。
- 为持续连接提供周期性有效性检查；空闲或没有新事件时也应在一个检查周期内关闭失效连接。
- 凭据失效统一以 4401 关闭连接，取消后台任务并释放所有进度订阅。
- 增加注销后新订阅、既有订阅推送、密码变更、令牌到期和空闲连接的回归覆盖，保留有效身份与跨用户拒绝行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/progress-streaming`：明确进度 WebSocket 在整个连接生命周期遵守令牌到期和会话撤销规则。

## Impact

预计业务交付文件为 `api/routes/ws.py` 和 `tests/test_api_ws.py`。复用现有认证服务及订阅接口，不引入依赖、数据库迁移或新协议消息。OpenSpec 产物使用中文。沿用当前干净工作区和 `main` 分支；tweak 预设为 direct/direct/off，执行相关回归及规格一致性验证。
