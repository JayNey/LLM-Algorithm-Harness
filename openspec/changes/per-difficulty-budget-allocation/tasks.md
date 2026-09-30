# Tasks: per-difficulty-budget-allocation

## Task 1: 每难度监控器编排

**文件**: `src/cost_strategy.py`、`tests/test_cost_strategy.py`

- [x] 提取 `result_cost(result)` 结算函数（已知定价成本 + unknown 标记），`RunCostMonitor.add_result` 改为复用，行为不变
- [x] `DifficultyBudgetMonitor`：难度→监控器字典、`add_result`、`over_cap_for`、`snapshot`
- [x] 单元测试：独立累计手算对账、难度间互不影响、未分配难度忽略、unknown 计数按难度归属

## Task 2: 配置与 CLI

**文件**: `src/models.py`、`src/main.py`、`tests/test_cost_strategy.py`

- [x] `HarnessConfig.budget_allocation: Optional[Dict[str, float]]`（值 gt=0，键校验）
- [x] `--budget-allocation DIFF=USD...` 解析；与映射绑定校验（无映射报错）、与 `--strategy` 互斥
- [x] 模型/CLI 测试：解析、重复键、非法值、无映射报错

## Task 3: Harness 集成与报告

**文件**: `src/harness.py`、`tests/test_cost_strategy.py`

- [x] 选择器模式构建每难度监控器；worker 按全局或所属难度触顶降级，日志区分触发来源
- [x] resume 回放按题目难度结算进各难度监控器
- [x] `_calculate_by_difficulty` 桶新增 `cost_usd`（已知定价累计，复用 `result_cost`）
- [x] Cost control 摘要逐难度输出预算使用
- [x] 端到端测试：easy 触顶只降级 easy 剩余题、medium/hard 不受影响；全局 cap 与分配 cap 并存；resume 后各难度独立生效；未启用时行为不变

## Task 4: 文档与回归

**文件**: `README.md`

- [x] 按难度预算分配使用说明（参数、独立降级语义、cost_usd 口径）
- [x] 全量测试 + `openspec validate` 通过
