## 1. 创建模块结构

- [x] 1.1 创建 `src/harness/cost/` 目录和 `__init__.py`，验证目录结构存在
- [x] 1.2 创建 `src/harness/cost/monitor.py` 模块文件，验证文件可导入

## 2. 实现 RealtimeCostPanel 类

- [x] 2.1 实现 `RealtimeCostPanel.__init__` 方法，接收 `cost_monitor`、`budget_monitor` 和 `total_problems` 参数，验证参数正确存储
- [x] 2.2 实现 `RealtimeCostPanel.update` 方法，更新已完成题目数，验证内部状态正确更新
- [x] 2.3 实现 `RealtimeCostPanel._get_budget_color` 方法，根据预算使用百分比返回颜色（绿/黄/红），验证三个阈值（< 80%、80-95%、> 95%）的颜色正确
- [x] 2.4 实现 `RealtimeCostPanel._render_overview` 方法，渲染总体成本概览部分（累计成本、预算使用、预计总成本），验证返回的 Table 包含正确的行和列
- [x] 2.5 实现 `RealtimeCostPanel._render_strategy_breakdown` 方法，渲染策略成本分布部分，验证多策略场景下显示正确
- [x] 2.6 实现 `RealtimeCostPanel._render_token_stats` 方法，渲染 token 使用统计部分，验证 prompt、completion 和 total tokens 显示正确
- [x] 2.7 实现 `RealtimeCostPanel.render` 方法，组合三个部分渲染完整面板，验证返回的 Table 包含所有部分
- [x] 2.8 实现 `RealtimeCostPanel.live` 上下文管理器，返回 `rich.live.Live` 对象，验证上下文管理器可正常进入和退出

## 3. 处理无预算配置场景

- [x] 3.1 在 `_render_overview` 中检查 `cost_monitor.budget_cap_usd` 是否为 `None`，动态隐藏预算相关行，验证无预算时不显示预算剩余和颜色预警
- [x] 3.2 添加单元测试验证无预算配置时的面板渲染行为，验证测试通过

## 4. 在 AlgorithmHarness 中集成面板

- [x] 4.1 在 `AlgorithmHarness._run_with_task_service` 方法中导入 `RealtimeCostPanel`，验证导入无错误
- [x] 4.2 在创建 `RunCostMonitor` 和 `DifficultyBudgetMonitor` 后创建 `RealtimeCostPanel` 实例，验证面板实例正确创建
- [x] 4.3 使用 `with panel.live():` 启动面板生命周期，包围任务执行逻辑，验证面板在评估期间保持活跃
- [x] 4.4 在 `_task_callback` 方法中调用 `panel.update(completed_count)` 更新面板，验证每完成一个题目后面板实时更新
- [x] 4.5 确保面板更新线程安全（复用 `progress_lock` 或创建独立锁），验证并发场景下无竞态条件

## 5. 添加单元测试

- [x] 5.1 创建 `tests/harness/cost/test_monitor.py` 测试文件，验证文件存在
- [x] 5.2 添加测试 `test_realtime_panel_with_budget`，验证有预算配置时面板渲染正确
- [x] 5.3 添加测试 `test_realtime_panel_without_budget`，验证无预算配置时面板渲染正确
- [x] 5.4 添加测试 `test_budget_color_thresholds`，验证颜色阈值（< 80%、80-95%、> 95%）正确
- [x] 5.5 添加测试 `test_panel_update`，验证 `update` 方法正确更新内部状态
- [x] 5.6 添加测试 `test_strategy_breakdown`，验证策略成本分布渲染正确
- [x] 5.7 添加测试 `test_token_stats`，验证 token 统计渲染正确
- [x] 5.8 运行所有新增测试并验证全部通过：`pytest tests/harness/cost/test_monitor.py -v`

## 6. 集成测试

- [x] 6.1 运行完整测试套件验证无回归：`pytest tests/ -v`
- [x] 6.2 使用真实数据集运行评估，验证实时面板正确显示并实时更新
- [x] 6.3 验证面板刷新不影响评估性能（对比开启和关闭面板的评估时间，差异应 < 5%）
- [x] 6.4 验证面板在有预算和无预算两种配置下均正常工作

## 7. 代码质量检查

- [x] 7.1 运行代码格式化工具（如 `black` 或 `ruff format`），验证代码格式符合项目规范
- [x] 7.2 运行代码检查工具（如 `ruff check`），验证无 linting 错误
- [x] 7.3 检查代码覆盖率，验证新增代码覆盖率 >= 80%：`pytest --cov=src/harness/cost tests/harness/cost/ --cov-report=term`
