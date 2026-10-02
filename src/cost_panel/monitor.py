"""实时成本监控面板模块。

使用 rich.live 在终端实时显示成本使用情况、预算预警和详细统计信息。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from rich.live import Live
from rich.table import Table

from src.cost_strategy import DifficultyBudgetMonitor, RunCostMonitor


class RealtimeCostPanel:
    """实时成本监控面板，展示累计成本、预算使用情况和详细统计。"""

    def __init__(
        self,
        cost_monitor: RunCostMonitor | None,
        budget_monitor: DifficultyBudgetMonitor | None,
        total_problems: int,
    ):
        """初始化实时成本面板。

        Args:
            cost_monitor: 运行级成本监控器
            budget_monitor: 难度级预算监控器
            total_problems: 总题目数
        """
        self.cost_monitor = cost_monitor
        self.budget_monitor = budget_monitor
        self.total_problems = total_problems
        self.completed_problems = 0
        self._live: Live | None = None
        # Token 统计累积
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0

    def update(self, completed_problems: int, result: Any = None) -> None:
        """更新已完成题目数并累积 token 统计。

        Args:
            completed_problems: 已完成的题目数
            result: 可选的执行结果，用于累积 token 统计
        """
        self.completed_problems = completed_problems

        # 从结果中累积 token 统计
        if result is not None:
            self.total_prompt_tokens += getattr(result, "prompt_tokens", 0) or 0
            self.total_completion_tokens += getattr(result, "completion_tokens", 0) or 0
            self.total_tokens += getattr(result, "total_tokens", 0) or 0

        if self._live is not None:
            self._live.update(self.render())

    def _get_budget_color(self, percentage: float) -> str:
        """根据预算使用百分比返回颜色。

        Args:
            percentage: 预算使用百分比 (0-100)

        Returns:
            颜色字符串: "green", "yellow", 或 "red"
        """
        if percentage < 80:
            return "green"
        elif percentage < 95:
            return "yellow"
        else:
            return "red"

    def _render_overview(self) -> Table:
        """渲染总体成本概览部分。

        Returns:
            包含成本概览的 Table 对象
        """
        table = Table(title="💰 成本概览", show_header=False, title_style="bold cyan")
        table.add_column("指标", style="cyan", no_wrap=True)
        table.add_column("数值", justify="right")

        # 累计成本
        accumulated_cost = Decimal("0")
        if self.cost_monitor is not None:
            accumulated_cost = self.cost_monitor.accumulated_cost
        table.add_row("累计成本", f"${accumulated_cost:.4f}")

        # 预算相关信息（仅在有预算配置时显示）
        if self.cost_monitor is not None and self.cost_monitor.budget_cap_usd is not None:
            budget_cap = self.cost_monitor.budget_cap_usd
            budget_used_pct = float((accumulated_cost / budget_cap) * 100) if budget_cap > 0 else 0
            budget_remaining = budget_cap - accumulated_cost

            # 根据预算使用百分比选择颜色
            color = self._get_budget_color(budget_used_pct)

            table.add_row("预算使用", f"[{color}]{budget_used_pct:.1f}%[/{color}]")
            table.add_row("预算剩余", f"[{color}]${budget_remaining:.4f}[/{color}]")

        # 预计总成本（基于已完成题目推算）
        if self.completed_problems > 0:
            avg_cost_per_problem = accumulated_cost / Decimal(self.completed_problems)
            projected_total = avg_cost_per_problem * Decimal(self.total_problems)
            table.add_row("预计总成本", f"${projected_total:.4f}")
            table.add_row("平均每题成本", f"${avg_cost_per_problem:.4f}")

        # 已完成进度
        table.add_row("已完成", f"{self.completed_problems}/{self.total_problems}")

        return table

    def _render_strategy_breakdown(self) -> Table:
        """渲染策略成本分布部分。

        Returns:
            包含策略成本分布的 Table 对象
        """
        table = Table(title="📊 难度成本分布", title_style="bold cyan")
        table.add_column("难度", style="cyan", no_wrap=True)
        table.add_column("累计成本", justify="right")
        table.add_column("预算上限", justify="right")
        table.add_column("占比", justify="right")

        if self.budget_monitor is None:
            # 无难度级预算监控器时显示提示
            table.add_row("N/A", "-", "-", "-")
            return table

        # 获取各难度的成本快照
        snapshots = self.budget_monitor.snapshot()

        if not snapshots:
            table.add_row("N/A", "-", "-", "-")
            return table

        # 计算总成本用于百分比
        total_cost = sum(Decimal(str(snap["accumulated_cost_usd"])) for snap in snapshots.values())

        # 按难度排序并显示
        for difficulty in sorted(snapshots.keys()):
            snap = snapshots[difficulty]
            cost = Decimal(str(snap["accumulated_cost_usd"]))
            budget_cap = snap["budget_cap_usd"]

            # 计算占比
            percentage = float((cost / total_cost) * 100) if total_cost > 0 else 0

            table.add_row(
                difficulty,
                f"${cost:.4f}",
                f"${budget_cap:.2f}" if budget_cap is not None else "-",
                f"{percentage:.1f}%",
            )

        return table

    def _render_token_stats(self) -> Table:
        """渲染 token 使用统计部分。

        Returns:
            包含 token 统计的 Table 对象
        """
        table = Table(title="🔢 Token 使用统计", title_style="bold cyan")
        table.add_column("类型", style="cyan", no_wrap=True)
        table.add_column("数量", justify="right")

        table.add_row("Prompt Tokens", f"{self.total_prompt_tokens:,}")
        table.add_row("Completion Tokens", f"{self.total_completion_tokens:,}")
        table.add_row("Total Tokens", f"{self.total_tokens:,}")

        # 如果有已完成的题目，显示平均值
        if self.completed_problems > 0:
            avg_tokens = self.total_tokens / self.completed_problems
            table.add_row("平均每题 Tokens", f"{avg_tokens:,.1f}")

        return table

    def render(self) -> Table:
        """渲染完整面板。

        Returns:
            包含所有部分的完整 Table 对象
        """
        from rich.console import Group

        # 组合所有部分
        overview = self._render_overview()
        strategy = self._render_strategy_breakdown()
        tokens = self._render_token_stats()

        # 使用 Group 将多个表格组合在一起
        return Group(overview, strategy, tokens)

    @contextmanager
    def live(self) -> Iterator[Live]:
        """返回 rich.live.Live 上下文管理器。

        Yields:
            Live 对象用于实时面板更新
        """
        self._live = Live(self.render(), refresh_per_second=4)
        try:
            with self._live:
                yield self._live
        finally:
            self._live = None
