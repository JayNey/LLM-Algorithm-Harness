## Why

登录用户可在实验或 A/B 测试中指定 `base_url`。Worker 会把带模型凭证的请求发往该地址，包括其网络可达的内网服务。

## What Changes

- **BREAKING** 实验与 A/B 测试的创建接口拒绝非空值（非 `null`）的 `base_url`。
- Worker 拒绝执行保存了地址覆盖值的历史任务。常规任务继续使用服务端的模型提供商端点。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/experiment-management` 增加实验与 A/B 测试的模型端点约束。

## Impact

涉及实验与 A/B 测试的请求校验、Worker 执行配置和回归测试。历史记录可继续查看。此前配置了地址覆盖值的待执行任务会以明确原因失败。
