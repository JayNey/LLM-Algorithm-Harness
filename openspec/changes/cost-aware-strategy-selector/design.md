# Design: 成本敏感策略选择器与运行中预算降级

## 实现说明

### 模块划分

新增 `src/cost_strategy.py`，两个类：

- `CostAwareSelector`：持有 `difficulty → strategy` 映射，`select(problem)` 返回策略名；构造时校验难度合法（easy/medium/hard）且策略在 `STRATEGY_MAP` 内。
- `RunCostMonitor`：线程安全的运行级成本台账。`add_result(result)` 从 `result.llm_traces` 累计已知定价成本（与 `harness._estimate_cost` 同口径：`pricing_metadata.total_cost` 且 `usage_known != False`）；usage 未知的结果不计入累计值、单独计数（`unknown_usage_results`），绝不当作零成本静默放行。`over_cap` 判断 `--budget-cap` 是否已达；`snapshot()` 输出 `{accumulated_cost_usd, budget_cap_usd, unknown_usage_results, downgraded_count}`。

### 集成点（TaskService 路径）

CLI `run` 固定走 `use_task_service=True`：

- 选择器模式下，任务单元从「策略 × 全部题目」改为「每题一个单元，策略取映射值」，单元 ID 规则不变（`{strategy}:{problem_id}:0`），天然兼容持久化与 resume。
- 数据集校验：题目难度必须全部被映射覆盖，否则启动即报错并列出未覆盖难度；映射策略必须存在于 `config.strategies`（提示补充配置）；`--strategy` 与映射互斥。
- worker 执行前检查 `monitor.over_cap`：未达上限用单元映射策略运行时；达上限改用映射中最便宜策略的运行时（固定成本阶梯 `multi_round_feedback > chain_of_thought > vanilla`，取映射中出现者的最低档），结果写 `strategy=实际策略` 并置 `cost_downgraded=True`。监控只约束本次运行的增量成本，不追溯历史运行。
- 报告与产物：选择器模式产出单一合并报告，报告名 `cost_aware`；`self.results["cost_aware"]` 为全部结果，每条结果带实际策略与 `cost_downgraded` 标记，`by_difficulty` 保留难度维度。stdout 在常规报告后追加成本控制摘要行。
- 串行路径（实验组合使用）不实现选择器：串行 + 选择器配置直接报错，保证 `harness experiment` 行为不变。

### 配置与 CLI

- `HarnessConfig` 新增 `difficulty_strategy: Optional[Dict[str, str]]`、`budget_cap_usd: Optional[float]`（gt=0）；配置文件与 CLI 等价。字段进入 `redacted_dict()`，config fingerprint 自动随之变化，resume 语义不变。
- `main.py` run 子命令新增 `--difficulty-strategy DIFF=STRATEGY...` 与 `--budget-cap USD`；`--budget-cap` 必须与映射同用，否则报错。

### 模型

`ExecutionResult` 新增 `cost_downgraded: bool = False`。纯增量字段，旧结果 JSON 校验不受影响。

## 边界

- 启发式：降级规则是确定性阶梯（达上限后一律最便宜策略），不做按题回退或预测，遵循 issue "不保证全局最优" 边界。
- usage 未知时无法真实约束成本：累计值只含已知定价部分，未知计数在摘要中显式呈现。
- 难度来自数据集标注，不在运行中做难度预测。
