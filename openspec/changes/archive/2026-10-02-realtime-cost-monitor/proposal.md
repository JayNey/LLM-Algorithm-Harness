## Why

当前成本追踪缺少实时可视化，用户无法直观了解成本使用情况和预算消耗进度。用户需要在评估运行过程中实时监控成本，并通过颜色预警及时发现预算超支风险。

## What Changes

- 新建 `src/harness/cost/monitor.py` 模块，实现基于 `rich.live` 的实时成本监控面板
- 在 `AlgorithmHarness` 中集成实时成本监控面板
- 实时显示累计成本、预算剩余百分比、预计总成本（基于已完成题目推算）
- 根据预算使用情况显示颜色预警：< 80% 绿色、80-95% 黄色、> 95% 红色
- 显示详细统计信息：每个策略的成本分布、平均每题成本、token 使用统计
- 确保面板更新不影响评估性能（异步更新机制）

## Capabilities

### New Capabilities

- `cost-monitoring/realtime-panel`: 实时成本监控面板功能，在终端显示成本使用情况、预算预警和详细统计

### Modified Capabilities

无现有能力的需求变更。

## Impact

- **新增文件**：`src/cost_panel/monitor.py`（新建目录 `src/cost_panel/`）
- **修改文件**：`src/harness.py`（集成实时面板）
- **依赖**：已有 `rich` 库，利用现有的 `RunCostMonitor` 和 `DifficultyBudgetMonitor`
- **用户体验**：用户在运行评估时能够实时看到成本面板，无需等待运行结束
- **性能**：使用 `rich.live` 的异步刷新机制，确保面板更新不阻塞主评估流程
