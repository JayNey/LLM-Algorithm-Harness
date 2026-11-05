## Context
自定义前缀已按键长度降序；内置前缀仍按字典顺序。详见 proposal.md。

## Decisions
内置字典遍历采用与自定义相同的长度降序排序。保留 override exact → custom exact/prefix → builtin exact/prefix → unknown 顺序，保持 PricingInfo 中原始请求模型名。
离线测试仅替换外部 SDK 调用，使用真实 LLMClient、PricingManager 和费用预算消费组件。

## Risks / Trade-offs
排序开销对于现有小字典可忽略。历史报告不重新计价；本次只纠正后续查询和执行的模型族匹配。
