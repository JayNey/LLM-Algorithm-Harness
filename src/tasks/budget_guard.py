"""Shared personal-budget enforcement for experiment/benchmark/A-B loops (#317).

评估 Worker 在逐单元边界检查 ``CostService.execution_budget`` 并按用户配置执行
pause/downgrade；实验、基准与 A/B 的 runner 只暴露无参 ``should_pause``，且切换
模型或策略会破坏对照与基准口径。因此本守卫的语义约定是：三类业务的
``budget.action`` 不论 pause 还是 downgrade，全局预算达到后都停止派发新单元，
并交给调用方按既有检查点机制暂停；恢复后重新进入循环时此处重查最新预算——
用户未调整预算则再次暂停，构成「检查点暂停」而非「暂停/恢复循环」。

已知边界：检查只统计已持久化费用，在途请求的花费要等提交后才可见，因此
known-cost 下限不是精确总额（与费用接口的完整性口径一致）。难度用量的统计与
预警经 ``execution_budget`` 覆盖三类业务；按难度暂停需要 runner 暴露下一单元
难度，三类业务 runner 目前只提供无参回调，未在本守卫实现。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from api.services.cost_service import CostService

logger = logging.getLogger(__name__)


class BudgetGuard:
    """Fresh personal-budget reads at dispatch boundaries; never raises."""

    def __init__(self, session_factory: Callable[[], Session], owner_id: str) -> None:
        self._session_factory = session_factory
        self.owner_id = owner_id
        self.last_state: dict[str, Any] | None = None

    def refresh(self) -> dict[str, Any] | None:
        """Re-read the owner's budget; a failed read lets execution continue.

        预算读取失败时选择放行而不是暂停：评估 Worker 的同名路径也只在读取
        成功时判定，且业务执行不应被预算子系统的瞬时故障放大。
        """
        try:
            with self._session_factory() as session:
                self.last_state = CostService.execution_budget(session, self.owner_id)
        except Exception as exc:  # noqa: BLE001 - 预算子系统故障不阻塞业务
            logger.warning("budget_guard_read_failed error_type=%s", type(exc).__name__)
            self.last_state = None
        return self.last_state

    def should_pause(self) -> bool:
        """True 当全局预算已用尽；此时调用方应停止派发并进入检查点暂停。"""
        state = self.refresh()
        if state is None:
            return False
        return bool(state.get("global_reached"))
