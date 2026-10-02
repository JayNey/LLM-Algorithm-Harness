"""单元测试：RealtimeCostPanel 实时成本监控面板。"""

from decimal import Decimal
from unittest.mock import Mock

from src.cost_panel.monitor import RealtimeCostPanel
from src.cost_strategy import DifficultyBudgetMonitor, RunCostMonitor


class TestRealtimeCostPanel:
    """测试 RealtimeCostPanel 类的各项功能。"""

    def test_realtime_panel_with_budget(self):
        """测试有预算配置时面板渲染正确。"""
        # 创建带预算的成本监控器
        monitor = RunCostMonitor(budget_cap_usd=10.0)
        monitor._accumulated_cost = Decimal("5.5")

        panel = RealtimeCostPanel(monitor, None, 100)
        panel.update(50)

        # 验证面板渲染
        overview = panel._render_overview()
        assert overview.title == "💰 成本概览"

        # 验证预算信息存在（通过渲染没有抛出异常来验证）
        rendered = panel.render()
        assert rendered is not None

    def test_realtime_panel_without_budget(self):
        """测试无预算配置时面板渲染正确。"""
        # 创建无预算的成本监控器
        monitor = RunCostMonitor(budget_cap_usd=None)
        monitor._accumulated_cost = Decimal("5.5")

        panel = RealtimeCostPanel(monitor, None, 100)
        panel.update(50)

        # 验证面板渲染（无预算信息）
        overview = panel._render_overview()
        assert overview.title == "💰 成本概览"

        rendered = panel.render()
        assert rendered is not None

    def test_budget_color_thresholds(self):
        """测试颜色阈值（< 80%、80-95%、> 95%）正确。"""
        panel = RealtimeCostPanel(None, None, 100)

        # 测试 < 80% 阈值
        assert panel._get_budget_color(0) == "green"
        assert panel._get_budget_color(50) == "green"
        assert panel._get_budget_color(79.9) == "green"

        # 测试 80-95% 阈值
        assert panel._get_budget_color(80) == "yellow"
        assert panel._get_budget_color(94.9) == "yellow"

        # 测试 > 95% 阈值
        assert panel._get_budget_color(95) == "red"
        assert panel._get_budget_color(100) == "red"
        assert panel._get_budget_color(150) == "red"

    def test_panel_update(self):
        """测试 update 方法正确更新内部状态。"""
        panel = RealtimeCostPanel(None, None, 100)

        # 初始状态
        assert panel.completed_problems == 0
        assert panel.total_prompt_tokens == 0
        assert panel.total_completion_tokens == 0
        assert panel.total_tokens == 0

        # 创建模拟结果
        result = Mock()
        result.prompt_tokens = 100
        result.completion_tokens = 50
        result.total_tokens = 150

        # 更新面板
        panel.update(5, result)

        # 验证状态更新
        assert panel.completed_problems == 5
        assert panel.total_prompt_tokens == 100
        assert panel.total_completion_tokens == 50
        assert panel.total_tokens == 150

        # 再次更新
        panel.update(10, result)
        assert panel.completed_problems == 10
        assert panel.total_prompt_tokens == 200
        assert panel.total_completion_tokens == 100
        assert panel.total_tokens == 300

    def test_strategy_breakdown(self):
        """测试策略成本分布渲染正确。"""
        # 创建带难度预算监控器的面板
        allocation = {"easy": 5.0, "medium": 10.0, "hard": 15.0}
        budget_monitor = DifficultyBudgetMonitor(allocation)
        budget_monitor.monitors["easy"]._accumulated_cost = Decimal("2.5")
        budget_monitor.monitors["medium"]._accumulated_cost = Decimal("7.3")
        budget_monitor.monitors["hard"]._accumulated_cost = Decimal("11.2")

        panel = RealtimeCostPanel(None, budget_monitor, 100)

        # 验证策略分布渲染
        strategy_table = panel._render_strategy_breakdown()
        assert strategy_table.title == "📊 难度成本分布"

        # 测试无监控器场景
        panel_no_monitor = RealtimeCostPanel(None, None, 100)
        table_no_monitor = panel_no_monitor._render_strategy_breakdown()
        assert table_no_monitor.title == "📊 难度成本分布"

    def test_token_stats(self):
        """测试 token 统计渲染正确。"""
        panel = RealtimeCostPanel(None, None, 100)
        panel.total_prompt_tokens = 1000
        panel.total_completion_tokens = 500
        panel.total_tokens = 1500
        panel.completed_problems = 10

        # 验证 token 统计渲染
        token_table = panel._render_token_stats()
        assert token_table.title == "🔢 Token 使用统计"

        # 测试空统计
        panel_empty = RealtimeCostPanel(None, None, 100)
        table_empty = panel_empty._render_token_stats()
        assert table_empty.title == "🔢 Token 使用统计"
