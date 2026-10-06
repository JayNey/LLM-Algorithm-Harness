## Why

当前项目缺少探索性搜索能力，在需要复杂规划的 hard 难度算法题上准确率受限。Tree of Thoughts (ToT) 策略通过多分支生成和搜索剪枝，可以系统地探索解题路径，预期在复杂题目上提升 10-20% 准确率。

## What Changes

- 新增 `TreeOfThoughtsStrategy` 类，实现基于搜索树的推理策略
- 支持 BFS 和 DFS 两种搜索模式
- 实现 `ThoughtNode` 数据结构表示思考树节点
- 实现节点质量评估机制（0-1 评分）
- 实现智能剪枝功能，基于质量阈值过滤低质量分支
- 添加配置参数：`branching_factor`（分支数）、`max_depth`（最大深度）、`search_strategy`（搜索策略）、`pruning_threshold`（剪枝阈值）
- 添加完整的单元测试（覆盖率 >= 90%）

## Capabilities

### New Capabilities

- `strategies/tree-of-thoughts`: Tree of Thoughts 策略的核心功能，包括多分支生成、搜索、评估和剪枝

### Modified Capabilities

<!-- 无需修改现有 capabilities 的 REQUIREMENTS -->

## Impact

- 新增文件：`src/strategies/tree_of_thoughts.py`
- 新增文件：`tests/test_tree_of_thoughts.py`
- 修改文件：`src/strategies/__init__.py`（注册新策略）
- 依赖：复用现有的 `StrategyBase`、`LLMClient`、`SandboxExecutor`
- 配置：新增策略配置项到 YAML 配置文件
