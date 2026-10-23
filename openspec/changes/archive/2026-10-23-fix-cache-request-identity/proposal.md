## Why
相同模型与提示在不同 provider/端点、thinking 开关或自定义生成参数下会错误复用缓存。根因：generate 已合并参数，但 CacheKey 只接收 temperature/max_tokens/system_prompt，且未包含端点身份。
## What Changes
- 将 provider、有效端点和完整合并生成参数纳入确定性缓存键。
- 更新键版本隔离旧条目；保留 problem_id/strategy_name，排除超时和重试策略。
- 添加错误复用回归测试并更新缓存说明。
## Capabilities
### Modified Capabilities
- `llm-response-cache`: 补全缓存键唯一性验收场景。
## Impact
仅修改缓存键、调用方、缓存集成测试和缓存文档，不改变 generate 接口或请求发送行为。

## 失败证据与根因消除
`python3 -m pytest tests/test_llm_client_cache.py::TestRequestIdentityCache -q --no-cov`：旧实现 12 failed / 2 passed；失败为预期 API 调用次数 1 或 2、实际 0 或 1，旧键返回 legacy。首次测试中 TokenUsage 缺少必填值已先修正，随后重新获得纯 bug 的失败证据。
修复后 14 passed；缓存/客户端相关 72 passed。调用点现在传入 provider、SDK 有效端点以及除 timeout 外全部 effective 参数；CacheKey 以 version=2 隔离旧缓存，原遗漏路径已消除。
