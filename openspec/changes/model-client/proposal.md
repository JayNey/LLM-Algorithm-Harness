# 提议：统一模型参数生效规则、响应兼容与 API 错误处理

## Problem

`StrategyConfig` 已声明温度、最大 token 和系统提示词，但三种策略没有把这些值传到实际请求。OpenAI 兼容服务、Anthropic 和本地服务的响应内容、usage 与错误行为也不一致，导致多轮评测可能丢失响应记录、错误重试过多，或把未知 usage 当成免费请求。

## Goal

- 明确定义全局 `LLMConfig` 与每个策略 `StrategyConfig` 的覆盖关系，并保存脱敏后的有效参数快照。
- 让 `local` 明确表示带 `base_url` 的 OpenAI 兼容服务，统一 OpenAI、SiliconFlow 和本地协议路径。
- 应用 Anthropic 请求超时，提供单一、有限且可测试的 429/5xx 重试策略，401/参数错误立即失败。
- 兼容字符串、多个文本块、空 content、可选 reasoning、截断响应和缺失 usage；未知计费标记为未知。

## Non-goals

- 不实现新的供应商 SDK 或自动发现本地服务地址。
- 不把模型 reasoning 自动拼进可执行代码，也不改变现有代码提取契约。
- 不提交 Comet/Claude 工作流生成的本地状态文件。

## Impact

影响 `src/models.py`、`src/llm_client.py`、策略调用链和成本汇总；现有 `generate(prompt, system_prompt=...)` 调用保持兼容。
