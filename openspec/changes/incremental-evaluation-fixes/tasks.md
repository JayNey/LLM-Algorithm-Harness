# Tasks: incremental-evaluation-fixes

## Task 1: 修复选集与历史加载

**文件**: `src/problem_loader.py`、`src/incremental/detector.py`、`src/main.py`

- [x] `filter_problems` 支持 `problem_ids` 白名单参数
- [x] `load_historical_results` 改为读取 run 目录内 `*_results.json`；`update_incremental_history`/main 传 run 目录
- [x] 单元测试：problem_ids 过滤、目录加载合并多策略

## Task 2: 修复合并报告重算

**文件**: `src/main.py`、`tests/test_incremental_e2e.py`

- [x] `merged_reports` 从合并结果真实重算全部指标（含成本/难度分布/formal）
- [x] 单元测试：合并指标与手算对账

## Task 3: 端到端闭环测试

**文件**: `tests/test_incremental_e2e.py`

- [x] 首跑全量 → 改数据集 → 二跑增量：只执行变化题、历史复用、合并报告完整
- [x] 回退分支：历史文件损坏、无匹配 run
- [x] 全量回归 + `openspec validate` + README 增量说明核对

## Task 4: 文档与交付

**文件**: `README.md`

- [x] 增量评估使用说明（触发条件、复用语义、回退行为）
- [x] 全量测试 + lint + `openspec validate` 通过
