# 轻量设计

## Context

动机与范围见 proposal.md。ABTestCreateRequest 接受完整 StrategyConfig 与 problem_filters；ABTestService 已保存并传入 ABTestConfig，ABTestRunner 在分组前使用 ProblemLoader 筛选，并把同一策略配置交给真实策略。PromptVariantClient 已实现变体 system_prompt 优先的共享规则。现有前端请求只发送 name/max_iterations，响应解析也丢弃高级配置。

## Decisions

1. 复用 experiments/advanced.ts 的策略参数白名单、JSON 校验和筛选归一；共享字段组件使用最小所需类型，使实验与 A/B 都可调用。避免复制白名单导致允许参数漂移。A/B 草稿新增可选字段以兼容旧草稿；独立策略温度输入与现有模型温度保持各自语义。
2. max_tokens 使用 100–8000 整数；非空 system_prompt 保留原文；custom_params 仅开放现有白名单，切换策略后按新策略重新校验。空字段省略，避免覆盖 #492 已实现的参数继承。
3. 筛选复用难度、逗号或换行列表及正整数 limit；请求去空、去重，ID 保留标点。创建页解释标签任一匹配、条件交集和最后截取，不预报未经执行核对的题数。响应保留配置，详情展示高级策略与筛选摘要。
4. 变体、基线、seed、并发和 prompt 覆盖均沿用共享逻辑。只在证据表明传递缺失时局部补齐，不调整分组算法、公开 schema 或 API 端点。
5. 字段错误就地显示；创建失败保留草稿，提交期间禁用配置与重复提交，重试清理旧反馈。

## Risks / Trade-offs

- 共享组件类型适配可能影响实验页：运行现有实验相关测试、TypeScript 构建和 lint。
- 配置到达 API 但未实际消费：离线测试经过请求模型、数据库持久化、ABTestConfig、真实 runner/策略及 mock LLM，断言有效参数、候选数、实际题目和提示词。
- 筛选后不足两个变体：保留 runner 现有错误并验证反馈。
- JSON 编辑易出错：展示允许参数与规则，校验未知键、类型、范围、枚举，失败后允许修正重提。

## Validation

前端验证空配置、有效/非法参数、筛选归一、响应保留、创建请求、失败修正重提和旧响应兼容。离线 Python 小题库与 mock LLM/sandbox 验证实际筛选、策略参数消费、默认继承、变体提示词优先级和基线/seed/并发保持。使用现有浏览器 mock 验收设施检查完整表单与详情；运行相关测试、前端构建、lint、格式检查和 OpenSpec 严格校验。不依赖付费模型或真实 Eval。
