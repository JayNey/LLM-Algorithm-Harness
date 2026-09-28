# Tasks: cost-aware-strategy-selector

## Task 1: 选择器与运行成本监控模块

**文件**: 新增 `src/cost_strategy.py`、`tests/test_cost_strategy.py`

- [x] `CostAwareSelector`：难度→策略映射、`select()`、难度与策略名校验
- [x] `RunCostMonitor`：`add_result()` 已知定价成本累计（与 `_estimate_cost` 同口径）、unknown usage 计数、`over_cap`、线程安全、`snapshot()`
- [x] 单元测试：映射校验、成本累计手算对账、unknown usage 不计入累计但计数、超限判定

## Task 2: 配置与结果模型

**文件**: `src/models.py`

- [x] `HarnessConfig` 新增 `difficulty_strategy`、`budget_cap_usd`（gt=0）并进入 redacted 快照
- [x] `ExecutionResult` 新增 `cost_downgraded: bool = False`
- [x] 模型测试：新字段默认值、旧结果 JSON 反序列化兼容

## Task 3: Harness 与 CLI 集成

**文件**: `src/harness.py`、`src/main.py`、`tests/test_cost_strategy.py`（集成测试）

- [x] TaskService 路径：选择器模式下按映射生成每题一个单元；难度全覆盖校验与映射策略存在性校验
- [x] worker 降级：`over_cap` 后改用映射中最便宜策略运行时，结果标记 `cost_downgraded` 与实际策略；监控只计本次运行增量
- [x] 选择器模式输出单一 `cost_aware` 合并报告；串行路径 + 选择器配置报错
- [x] CLI：`--difficulty-strategy DIFF=STRATEGY...`、`--budget-cap USD`；互斥与依赖校验（与 `--strategy` 互斥、`--budget-cap` 需映射）；stdout 成本控制摘要
- [x] 端到端测试（mock LLM）：映射路由正确、达上限后降级标记正确、未启用时行为与现状一致

## Task 4: 文档与回归

**文件**: `README.md`

- [x] 成本敏感策略选择器使用说明：参数、映射规则、降级语义、unknown usage 口径
- [x] 全量测试 + `openspec validate` 通过
