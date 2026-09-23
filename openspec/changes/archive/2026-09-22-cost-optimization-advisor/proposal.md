# Proposal: 成本优化建议（预算优化器与三目标推荐）

## Why

#46/#48/#65 合并后，实验对比数据（组合级准确率、成本、性价比排名、按难度分布）已经齐备，但用户仍需手动从 comparison.json 里挑配置。issue #56 要求基于历史数据直接给出推荐：三目标最优组合、给定预算下的最优评估方案。本次实现分析推荐层（#56a）；issue 中"成本敏感策略选择器 + 运行中预算降级"涉及执行流程改动，拆分为后续独立 change（#56b），不在本 change 范围。

## What Changes

- 新增 `src/cost_optimizer.py`，消费已有实验的 `comparison.json`：
  - **性价比排名表**：复用 #65 的 `model_comparison.cost_effectiveness` 与组合级数据，输出 (模型, 策略, 准确率, 成本, 性价比) 排名；成本未知的组合标注"未知"并排除。
  - **三目标推荐**：`highest_accuracy`（不看成本）/ `best_value`（性价比最高）/ `lowest_cost`（满足最低准确率约束下最便宜），每目标给出推荐组合与依据。
  - **预算优化器**：输入预算与最低准确率约束，按难度分层（easy/medium/hard）从历史 by_difficulty 数据中为每层挑选"单位成本通过数最高且达标"的组合，估算总成本、预期准确率与可覆盖题数（启发式贪心，不保证全局最优，遵循 issue 边界）。
- 新增 CLI：`harness optimize --experiment <dir> [--budget N] [--min-accuracy X] [--objective ...]`，输出 `optimization.json` 与 `OPTIMIZATION.md` 到实验目录并打印摘要。
- 文档：`docs/experiments.md` 新增成本优化使用指南（推荐口径、启发式边界）。

## Capabilities

### New Capabilities

- `cost-optimization`: 基于历史实验数据的性价比分析、三目标组合推荐与预算优化器。

### Modified Capabilities

（无——只读消费 comparison.json，不改变实验执行与既有产物格式）

## Impact

- 代码：新增 `src/cost_optimizer.py`；`src/main.py` 新增 `optimize` 子命令；新增 `tests/test_cost_optimizer.py`；`docs/experiments.md`、README 更新。
- 兼容性：`optimize` 是独立分析命令，不触碰 `run`/`import`/`experiment` 执行路径；输入为已完成实验的 comparison.json。
