# strategies/tree-of-thoughts Specification

## Purpose
Enables algorithmic problem solving through multi-branch exploration, evaluating multiple reasoning paths simultaneously to identify optimal solutions for complex problems.

## Requirements

### Requirement: Multi-branch thought generation
The strategy SHALL generate multiple candidate reasoning branches at each decision point, allowing parallel exploration of different solution approaches.

#### Scenario: Generate branches at root node
- **WHEN** strategy begins solving a problem
- **THEN** system creates N child nodes (where N equals branching_factor) with distinct reasoning approaches

#### Scenario: Generate branches at intermediate node
- **WHEN** a non-leaf node is selected for expansion
- **THEN** system generates branching_factor new child nodes exploring different next steps

#### Scenario: Respect branching factor configuration
- **WHEN** branching_factor is set to 3
- **THEN** each node expansion produces exactly 3 child branches

### Requirement: Search strategy execution
The strategy SHALL support both breadth-first search (BFS) and depth-first search (DFS) traversal modes for exploring the thought tree.

#### Scenario: BFS explores level by level
- **WHEN** search_strategy is "bfs"
- **THEN** all nodes at depth N are explored before any node at depth N+1

#### Scenario: DFS explores depth first
- **WHEN** search_strategy is "dfs"
- **THEN** system explores one branch to maximum depth before backtracking to explore siblings

#### Scenario: Respect max depth limit
- **WHEN** max_depth is set to 4
- **THEN** no node deeper than depth 4 is expanded

### Requirement: Node quality evaluation
The strategy SHALL evaluate each thought node with a quality score between 0.0 and 1.0, indicating the promise of that reasoning path.

#### Scenario: Score promising nodes high
- **WHEN** a node contains logical, well-structured reasoning toward the solution
- **THEN** quality_score is >= 0.7

#### Scenario: Score unpromising nodes low
- **WHEN** a node contains contradictory logic or incorrect assumptions
- **THEN** quality_score is < 0.3

#### Scenario: Score is bounded
- **WHEN** any node is evaluated
- **THEN** quality_score is between 0.0 and 1.0 inclusive

### Requirement: Intelligent branch pruning
The strategy SHALL remove low-quality branches from the search space based on a configurable quality threshold.

#### Scenario: Prune below threshold
- **WHEN** a node's quality_score is below pruning_threshold
- **THEN** that node and all its descendants are excluded from further exploration

#### Scenario: Keep above threshold
- **WHEN** a node's quality_score is at or above pruning_threshold
- **THEN** that node remains eligible for expansion

#### Scenario: Pruning reduces search space
- **WHEN** 5 branches are generated and 2 score below threshold 0.3
- **THEN** only 3 branches continue in the search

### Requirement: Solution extraction
策略 SHALL 从已探索分支中选择含非空白代码的最高分叶子，并在最终结果中保存同一份代码。

#### Scenario: Return highest scoring leaf
- **WHEN** 搜索完成或达到 max_depth，不论单层或多层、BFS 或 DFS、兄弟遍历顺序
- **THEN** generated_code 等于所选最高分有效叶子的代码，公开或反馈执行使用同一份代码

#### Scenario: Handle no valid solution
- **WHEN** 没有叶子、所有分支被剪枝且没有有效叶子代码，或所有叶子代码为空白
- **THEN** 返回失败，failure_category 为 code_extraction_failed，generated_code 为空，不执行空代码

#### Scenario: Hidden evaluation uses selected code
- **WHEN** ToT 公开测试通过且题目含隐藏用例
- **THEN** Harness 使用结果中同一份所选代码执行 hidden，隐藏失败时最终结果必须失败

#### Scenario: Preserve selected code on execution failure
- **WHEN** 所选代码公开执行失败或沙箱异常
- **THEN** 结果保持失败并保存所选代码，执行结果可用时予以保留

### Requirement: Iteration tracking
The strategy SHALL track and record all exploration iterations including node expansions, evaluations, and pruning decisions.

#### Scenario: Record node expansions
- **WHEN** any node is expanded into child branches
- **THEN** iteration result captures parent node state, generated children, and expansion timestamp

#### Scenario: Record quality scores
- **WHEN** any node is evaluated
- **THEN** iteration result includes the node's quality_score and evaluation reasoning

#### Scenario: Record pruning events
- **WHEN** branches are pruned
- **THEN** iteration result identifies which nodes were removed and why

### Requirement: Configuration validation
The strategy SHALL validate configuration parameters and reject invalid values.

#### Scenario: Validate branching factor
- **WHEN** branching_factor is less than 1
- **THEN** system raises configuration error

#### Scenario: Validate max depth
- **WHEN** max_depth is less than 1
- **THEN** system raises configuration error

#### Scenario: Validate search strategy
- **WHEN** search_strategy is neither "bfs" nor "dfs"
- **THEN** system raises configuration error

#### Scenario: Validate pruning threshold
- **WHEN** pruning_threshold is not between 0.0 and 1.0
- **THEN** system raises configuration error

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
