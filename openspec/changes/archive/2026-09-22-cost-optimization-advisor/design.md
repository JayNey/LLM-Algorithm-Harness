# Design: 成本优化建议

## 实现说明

### 数据来源

只读消费已完成实验的 `comparison.json`：组合级 `solved`/`pass_rate_over_total`/`cost`、`model_comparison.cost_effectiveness`（#65 产出）、`by_difficulty`。不重跑评测。

### 推荐引擎（src/cost_optimizer.py）

- `rank_combinations(comparison)`：每组合一行 (model, strategy, accuracy=solved/total, cost, ratio=solved/cost)；cost 未知或 ≤0 → `available: false`，标注"未知"，不进排名。
- `recommend(comparison, objective, min_accuracy)`：
  - `highest_accuracy`：pass_rate_over_total 最高者；
  - `best_value`：ratio 最高者；
  - `lowest_cost`：pass_rate ≥ min_accuracy 的组合中 cost 最低者；无达标 → `feasible: false` + 说明。
- `optimize_budget(comparison, budget, min_accuracy)`：对 easy/medium/hard 三层，取该层 by_difficulty 下"每美元通过数最高且准确率 ≥ min_accuracy"的组合（各层数据来自该 (模型,策略) 组合的 by_difficulty 分组），层成本按该组合单位成本 × 层题数估算；累计超过预算的层跳过并标注；无历史数据的层标注"无历史数据"。输出 `{layers, estimated_cost, estimated_accuracy, coverage}`。

### CLI（src/main.py）

`harness optimize --experiment <dir> [--budget N] [--min-accuracy X] [--objective highest_accuracy|best_value|lowest_cost]`：
- 读 comparison.json（缺失/损坏 → 报错退出码 1）；
- 无 --budget 时只输出排名 + 三目标推荐；有 --budget 时追加优化方案；
- 写 `optimization.json` + `OPTIMIZATION.md` 到实验目录，stdout 打印摘要。

### 边界

- 启发式贪心，不保证全局最优（issue 边界原话）；推荐基于历史数据。
- "成本敏感策略选择器 + 运行中预算降级"（issue 第 4 节）拆分为后续独立 change，本 change 不触碰执行路径。

### 测试策略

- 手工构造小 comparison.json（3 组合：便宜低准确率 / 贵高准确率 / 中等）：三目标推荐各自命中预期组合；min_accuracy 无达标时 feasible=false。
- 预算优化器：按层手算单位成本选出预期组合、estimated_cost ≤ budget、无数据层标注。
- CLI：端到端跑 optimize 断言产物与退出码；缺 comparison.json 时非零退出。
