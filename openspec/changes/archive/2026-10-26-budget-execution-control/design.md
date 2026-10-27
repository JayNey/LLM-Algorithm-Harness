## Context

评估由 TaskService 串行运行策略×题目单元，主线程检查暂停、结算成本，执行线程不访问数据库。个人 Budget 已持久化。

## Decisions

- 用户选择 A2：知悉跨模块协调，继续 Tweak，在 codex/tweak/20261026/budget-execution-control 分支实现。
- 本 change 接入 Web 评估任务的个人预算控制。全局统计沿用成本查询口径：用户评估累计支出与已完成 benchmark；固定预算实验、AB test 和 benchmark 内部调度不是此次评估执行接入的改造对象。
- 成本服务提供基于调用方 session 的执行预算快照，无新 HTTP API、schema 或依赖。派发前重读个人配置、全局成本和结果的分难度实际已知成本。页面保留难度估算展示；执行账本仅使用可归属难度的实际成本，缺失难度仅参与全局用量。
- 达到任一适用上限即执行保存的动作。pause 在下一个超限单元前暂停评估并保留队列；downgrade 使用最低阶梯 vanilla，目标本已是 vanilla 时继续。单任务上限及手动暂停优先。
- 主线程决定单元实际策略，执行线程只读取选择；必要时主线程准备 vanilla runtime。
- 保持单元和数据库结果的原策略键，避免多策略降级后冲突；结果 metrics 另记 executed_strategy 与 cost_downgraded。恢复重新检查当前预算，不重新调度已完成单元、不重复累计成本。

## Risks / Trade-offs

- 以单元边界控制，在途单元可能越过上限；跨任务并发不预留额度，不能保证模型调用前的硬金额限流。
- 未知成本不虚构，继续记录 cost_unknown；旧结果缺少难度时只参与全局用量。
- 降级影响策略可比性，通过实际策略与降级标记追溯。

## Migration Plan

无需迁移。部署 worker 后对新任务及恢复任务生效，回滚 worker 即恢复原行为。
