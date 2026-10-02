## Context

当前成本追踪通过 `RunCostMonitor` 和 `DifficultyBudgetMonitor` 在内存中累积成本，但没有实时可视化。评估运行通过 `rich.progress.Progress` 显示进度条，但不显示成本信息。`AlgorithmHarness` 在 `_run_with_task_service` 方法中协调评估流程，使用 `TaskService` 管理任务队列和并发执行。

参见 proposal.md - Why 了解动机。

## Goals / Non-Goals

**Goals:**
- 在终端实时显示成本监控面板，展示累计成本、预算使用情况和详细统计
- 复用现有的 `RunCostMonitor` 和 `DifficultyBudgetMonitor` 作为数据源
- 使用 `rich.live` 实现非阻塞的实时刷新
- 支持有预算和无预算两种配置场景

**Non-Goals:**
- 不修改现有的成本追踪逻辑（`RunCostMonitor`、`DifficultyBudgetMonitor`、`result_cost`）
- 不替换现有的进度条显示（`rich.progress.Progress`）
- 不引入新的成本计算方式或数据源
- 不支持自定义面板布局或主题

## Decisions

### 决策 1: 使用 `rich.live.Live` 实现实时面板

**选择:** 使用 `rich.live.Live` 上下文管理器创建实时更新的面板。

**理由:**
- `rich.live` 提供非阻塞的实时刷新，不影响主评估流程
- 与现有的 `rich.progress.Progress` 兼容，可以在同一终端同时显示
- 支持自动刷新频率控制（默认 4 次/秒）
- 提供清晰的生命周期管理（`__enter__`、`__exit__`）

**备选方案:**
- 使用 `rich.console.Console.print` 手动刷新：需要手动清屏和重绘，性能较差且可能闪烁
- 使用 `rich.table.Table` 静态表格：无法实时更新，不满足需求

### 决策 2: 创建独立的 `RealtimeCostPanel` 类

**选择:** 在新模块 `src/harness/cost/monitor.py` 中创建 `RealtimeCostPanel` 类，封装面板逻辑。

**理由:**
- 单一职责：面板类只负责数据展示，不负责成本计算
- 可测试性：独立类便于单元测试
- 可复用性：未来可以在其他评估场景中复用
- 符合项目结构：将成本相关功能集中在 `src/harness/cost/` 目录下

**接口设计:**
```python
class RealtimeCostPanel:
    def __init__(
        self,
        cost_monitor: RunCostMonitor | None,
        budget_monitor: DifficultyBudgetMonitor | None,
        total_problems: int,
    ):
        ...
    
    def update(self, completed_problems: int) -> None:
        """更新已完成题目数，触发面板刷新"""
    
    def render(self) -> Table:
        """渲染当前面板内容为 rich.table.Table"""
```

### 决策 3: 在 `AlgorithmHarness` 中集成面板

**选择:** 在 `_run_with_task_service` 方法中创建并启动实时面板，在任务回调中更新面板。

**理由:**
- `_run_with_task_service` 是使用 `RunCostMonitor` 的唯一路径，与面板需求匹配
- 已有 `progress` 和 `progress_lock` 用于线程安全的进度更新，可复用该模式
- 任务回调（`_task_callback`）是更新成本的自然位置

**集成点:**
1. 在创建 `RunCostMonitor` 和 `DifficultyBudgetMonitor` 后创建 `RealtimeCostPanel`
2. 使用 `with panel.live():` 启动面板生命周期
3. 在 `_task_callback` 中调用 `panel.update(completed_count)` 更新面板

### 决策 4: 颜色预警使用 `rich.style.Style`

**选择:** 使用 `rich.style.Style` 动态设置颜色，基于预算使用百分比。

**理由:**
- `rich.style.Style` 支持终端原生颜色，兼容性好
- 动态颜色设置简单直观：`Style(color="green")` / `"yellow"` / `"red"`
- 符合 spec 要求的三段阈值（< 80%、80-95%、> 95%）

**颜色映射:**
```python
def _get_budget_color(self, percentage: float) -> str:
    if percentage < 80:
        return "green"
    elif percentage < 95:
        return "yellow"
    else:
        return "red"
```

### 决策 5: 面板布局使用 `rich.table.Table`

**选择:** 使用 `rich.table.Table` 渲染面板，分为三个部分：
1. 总体成本概览（累计成本、预算使用、预计总成本）
2. 策略成本分布（每个策略的成本和占比）
3. Token 使用统计（prompt、completion、total tokens）

**理由:**
- `Table` 提供清晰的行列结构，易于阅读
- 支持颜色、样式和对齐
- 可动态添加行，适应不同策略数量

**备选方案:**
- 使用 `rich.panel.Panel` 嵌套多个组件：结构复杂，刷新性能较差
- 使用纯文本格式化：缺少视觉层次，可读性差

## Risks / Trade-offs

**[风险] 面板刷新可能影响终端性能**
→ **缓解:** `rich.live` 默认限制刷新频率为 4 次/秒（250ms 间隔），足够流畅且不会过载终端。在 spec 中明确该性能要求。

**[风险] 多线程并发更新可能导致数据不一致**
→ **缓解:** `RunCostMonitor` 和 `DifficultyBudgetMonitor` 已使用 `threading.Lock` 保护内部状态。`RealtimeCostPanel` 只读取这些监控器的数据，不修改状态，避免竞态条件。

**[风险] 无预算配置时显示内容不完整**
→ **缓解:** 在 `RealtimeCostPanel` 中检查 `cost_monitor.budget_cap_usd` 是否为 `None`，动态隐藏预算相关行（预算剩余、颜色预警）。在 spec 中明确该场景的行为。

**[权衡] 创建新目录 `src/harness/cost/` 增加项目结构复杂度**
→ **理由:** 当前成本相关文件分散在根目录（`src/budget.py`、`src/cost_strategy.py`、`src/cost_alert.py`），未来可能有更多成本功能（如成本优化、成本分析）。创建独立目录为未来扩展提供清晰的组织结构。

**[权衡] 面板与进度条同时显示可能占用较多终端空间**
→ **理由:** 成本信息对用户决策至关重要，值得占用额外空间。用户可通过调整终端窗口大小或禁用进度条（未来功能）来管理空间。

## Migration Plan

**部署步骤:**
1. 创建 `src/harness/cost/` 目录和 `monitor.py` 模块
2. 实现 `RealtimeCostPanel` 类，包含单元测试
3. 在 `AlgorithmHarness._run_with_task_service` 中集成面板
4. 更新相关配置文档，说明实时面板功能

**回滚策略:**
- 如果面板导致终端兼容性问题，可通过配置项 `enable_realtime_cost_panel: false`（默认 `true`）禁用面板
- 面板代码独立，删除集成代码即可完全回滚，不影响现有成本追踪功能

**兼容性:**
- 依赖 `rich` 库版本 >= 10.0（项目已满足）
- 仅在 `use_task_service=True` 路径启用，不影响固定预算实验路径

## Open Questions

无需延迟解决的问题。
