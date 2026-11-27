# Preset file-count authorization

- status: active
- workflow: tweak
- decision: continue-on-file-count-only
- scope: issue #526 已批准方案中的高级策略字段、筛选、组合预算、回显、兼容及离线测试；预估 10–14 个交付文件。
- allowed-file-categories: implementation, tests, user-docs, config, generated
- authorization-basis: user-explicit
- reason: 用户在 Open 确认选择 A，批准上述方案及范围不变时超过 6 文件继续 tweak。复用已有 API、StrategyConfig、ProblemLoader 和 ProblemBudget，无新增端点、共享 schema 或跨层架构设计。
