## 1. 参数与 provider 协议

- [x] 1.1 将策略级 temperature、max_tokens、system_prompt、custom_params 传入实际请求并记录脱敏快照
- [x] 1.2 将 local 约束为显式 base_url 的 OpenAI 兼容 provider，保留 SiliconFlow 预设
- [x] 1.3 将 Anthropic timeout 应用到 Messages API 请求

## 2. 错误、重试与响应

- [x] 2.1 关闭 SDK 隐式重试，增加带总次数、退避和总耗时上限的 429/5xx 重试
- [x] 2.2 对 401/参数错误立即失败，并统一脱敏 provider 错误
- [x] 2.3 兼容多文本块、空/截断 content、可选 reasoning 和缺失 usage
- [x] 2.4 将未知 usage 标记为 unknown，成本汇总不把它当作免费调用

## 3. 验证与文档

- [x] 3.1 增加 OpenAI、Anthropic、local、覆盖参数和重试行为测试
- [x] 3.2 运行全量测试、Python 编译检查和严格 OpenSpec 校验（仓库既有 Ruff 告警另行记录）
