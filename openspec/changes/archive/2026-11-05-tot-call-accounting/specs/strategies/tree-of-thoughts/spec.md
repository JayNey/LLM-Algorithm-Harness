## ADDED Requirements

### Requirement: Complete model call accounting
策略 SHALL 为每次已发生的分支生成及节点评分调用保存独立、可审计且脱敏的轨迹；沿用已有 token 和定价语义，禁止按树节点重复计费或因剪枝丢失已发生的调用。

#### Scenario: Generation and evaluation settlement
- **WHEN** 一次生成和一次评分各返回 150 token、已知费用 $0.01
- **THEN** 结果含两条调用轨迹、300 token、费用 $0.02，运行成本 cap $0.01 触发，实验 ledger 与结果的已知 token 一致

#### Scenario: Branching and pruning
- **WHEN** BFS 或 DFS 探索多层多分支并剪枝
- **THEN** 所有已发生调用恰好记录一次，轨迹可区分生成与评分以及节点深度

#### Scenario: Failures and budget stops
- **WHEN** 解析失败、模型调用失败或预算拒绝后续调用
- **THEN** 已有调用用量和费用保留，模型失败轨迹保留错误和未知用量，预算拒绝不产生虚假调用且结果标记预算停止

#### Scenario: Missing usage and pricing
- **WHEN** 用量缺失、价格未知或已知零价
- **THEN** 保留响应中的未知标记和原始定价语义，未知费用不能伪装为已知免费
