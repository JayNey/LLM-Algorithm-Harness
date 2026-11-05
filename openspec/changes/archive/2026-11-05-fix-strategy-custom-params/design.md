## Context
内部控制键与合法生成扩展共用 custom_params。内置策略消费键的完整清单为 num_candidates、num_examples、similarity_metric、min_similarity_score、example_source、reflection_context_chars；temperature 为合法生成字段。

## Decisions
在 StrategyBase 生成 provider 参数副本时剔除这六个控制键，供基类 generate 和 Self-Consistency 直接调用复用。保留配置原字典供检索、候选数和反思长度消费。不在通用 LLMClient 引入策略知识，也不使用 SDK 参数白名单，以支持合法扩展。
保留现有显式参数与 custom_params 覆盖顺序；过滤发生于 effective_params 与缓存键形成之前。Anthropic 现有 extra_body 被排除却未转交 SDK，修复其合法扩展透传以满足 issue 验收。

## Risks / Trade-offs
未来新增内部键需更新过滤清单。用真实 SDK 的本地 transport 测试覆盖三个 provider 路径、三个策略入口、参数优先级与缓存命中/失效；不访问付费模型。

## 验证环境
真实请求边界使用 OpenAI 3.13.0、Anthropic 0.49.0，所有请求由本地 MockTransport 返回。宿主 Anthropic 1.5.0 已移除 temperature/top_p，与主线现有请求格式不兼容；该独立兼容性问题不在 #348 内，未通过改动生产参数语义规避。测试 transport 兼容两代 HTTP 库。
