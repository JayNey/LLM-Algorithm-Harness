## ADDED Requirements

### Requirement: 基准运行预算上限执行

系统 SHALL 在基准运行请求携带 `budget_cap_usd` 时按题目单元累计已知成本；达到或超过上限后 SHALL 在下一个单元派发前暂停运行，保留已完成结果与检查点，并把 run 及关联 AsyncTask 置为 `paused`，MUST NOT 直接失败或继续派发新单元。用户恢复运行 SHALL 重放已完成单元、只继续未完成单元，并重新判断预算；预算仍不足时 SHALL 再次暂停。未提供 `budget_cap_usd` 时 SHALL 保持现有完成行为。个人预算守卫与用户手动暂停/取消 SHALL 继续生效。

#### Scenario: 达到预算后暂停

- **WHEN** 基准运行的已知成本达到 `budget_cap_usd`，且仍有未派发单元
- **THEN** 运行在单元边界暂停，run 与任务为 `paused`，已完成题目的结果与检查点保留，后续单元不执行

#### Scenario: 未达到预算正常完成

- **WHEN** 基准运行完成时已知成本低于 `budget_cap_usd`
- **THEN** 运行按现有流程完成并持久化 accuracy、cost、结果摘要

#### Scenario: 恢复后重新判断且不重复执行

- **WHEN** 用户恢复一个因预算暂停的基准运行
- **THEN** 已完成题目从检查点重放且不重新调用模型，剩余单元继续执行；累计成本仍达到上限时再次暂停

#### Scenario: 无预算运行保持不变

- **WHEN** 基准运行请求没有 `budget_cap_usd`
- **THEN** 执行路径、暂停/取消行为与运行结果与变更前一致
