# Tasks: 成本优化建议

## Task 1: 排名与三目标推荐

**文件**: 新增 `src/cost_optimizer.py`

- [x] `rank_combinations`：性价比排名（成本未知/为零排除并标注"未知"）
- [x] `recommend`：highest_accuracy / best_value / lowest_cost（含 min_accuracy 约束与 feasible=false 分支）
- [x] 单元测试：手工 comparison.json 三目标各自命中预期；未知成本排除

## Task 2: 预算优化器

**文件**: `src/cost_optimizer.py`

- [x] `optimize_budget`：按难度分层贪心选择（单位成本通过数最高且达标），估算成本/准确率/覆盖
- [x] 预算超限层跳过标注；无历史数据层标注
- [x] 单元测试：分层选择与成本上限手算对账

## Task 3: CLI 与产物

**文件**: `src/main.py`

- [x] `harness optimize --experiment <dir> [--budget] [--min-accuracy] [--objective]` 子命令
- [x] 写 `optimization.json` + `OPTIMIZATION.md`，stdout 摘要；缺输入报错退出码 1
- [x] 端到端测试：产物与退出码断言；缺输入报错断言

## Task 4: 文档与回归

**文件**: `docs/experiments.md`, `README.md`

- [x] 成本优化使用指南（三目标、启发式边界、与 #65 数据关系）
- [x] 全量测试 + OpenSpec validate 通过
