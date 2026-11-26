# 设计

## Context

动机与范围见 proposal.md，行为契约见 specs/frontend/experiments-management/spec.md。当前 OptimizeTab 仅提交 objective，并在 loading/error 时提前返回，导致表单和重试入口缺失。现有客户端已传 budget/min_accuracy，但响应解析丢弃 layers 并把 estimated_accuracy=null 转为 0。现有共享算法的三目标与预算分层语义保持不变。

## Decisions

- 在现有 OptimizeTab 内维护字符串输入及字段错误；预算校验有限正数，准确率使用百分比输入并除以 100；空值不传。复用 useResource 的加载标识与 AbortSignal 隔离迟到响应，非法输入时不提交分析请求。
- 表单始终渲染，结果区独立展示加载、可重试错误或成功结果。输入变化即失效旧结果，与现有目标选择即时加载行为一致。
- 扩充现有 OptimizeAdvisory 类型及严格响应解析，保留难度层信息与 nullable 预期准确率，不伪造无数据指标；预算结果使用汇总与难度层表格。
- 使用现有国际化资源提供新增文案。直接实施、直接测试、review off，遵循 tweak Runtime 配置。
- 使用现有 Node 客户端测试、Playwright 浏览器 fixture 和 Python API 测试设施，固定 comparison 数据验证 budget/min_accuracy 经客户端及 API 到达共享 build_advisory 并影响真实结果。以构建、lint、格式检查及相关回归覆盖交付。

## Risks / Trade-offs

- 每次编辑可能重新请求：沿用既有即时目标选择行为，并通过取消与结果标识避免旧数据覆盖。
- 预算分层为现有历史启发式方案，不保证全局最优；页面说明约束适用范围及历史估算性质。
- 兼容既有无 budget_plan 响应；不改共享算法、API schema、CLI、权限或部署配置。相关回归不使用付费模型。

## Migration Plan

无数据迁移或新依赖。前端构建交付；回退本次代码即可恢复原页面。
