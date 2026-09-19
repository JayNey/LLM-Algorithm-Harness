# 设计：统一模型客户端协议

## 参数优先级

每次策略调用都显式传递 `system_prompt`、`temperature`、`max_tokens` 和 `custom_params`。客户端用策略传入的非空覆盖值替换全局配置；没有覆盖时使用 `LLMConfig`。`model`、`timeout` 和认证信息始终由全局配置控制。请求完成后，响应携带不含 prompt、密钥或认证信息的有效参数快照，并由策略写入每轮 trace。

## provider 与协议

`openai`、`siliconflow` 和 `local` 共用 OpenAI Chat Completions 协议。`siliconflow` 保留既有预设地址；`local` 必须显式提供 `base_url`，空 key 时使用 SDK 所需的本地占位值。Anthropic 继续使用 Messages API，并把配置的 timeout 传到真实请求。

## 重试与错误

SDK 内置重试关闭，客户端统一执行最多 `retry_max_attempts` 次调用。仅 429、5xx、超时和连接类错误重试，按指数退避并受 `retry_max_elapsed_seconds` 限制；401/403、其它 4xx 和参数错误直接失败。异常在离开客户端前统一脱敏。

## 响应归一化

OpenAI message content 与 Anthropic content block 统一提取文本块并拼接；thinking/reasoning 块单独放入 `reasoning_text`，不混入代码文本。空 content 返回空字符串并保留 finish reason、usage_missing 与 trace。缺失 usage 的 pricing metadata 使用 `usage_known=false` 与 `total_cost=null`，汇总只计算已知成本并标记 `unknown_usage`。
