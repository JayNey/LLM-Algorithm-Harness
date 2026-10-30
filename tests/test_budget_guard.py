"""BudgetGuard 语义单元测试（#317）。

约定见 src/tasks/budget_guard.py 模块文档：三类业务不论 pause/downgrade 都在
全局预算用尽时暂停；读取失败放行；按难度暂停需要 runner 暴露下一单元难度，
不在本守卫实现。
"""

import contextlib

from src.tasks.budget_guard import BudgetGuard


def _state(
    global_reached: bool = False,
    exhausted: tuple[str, ...] = (),
    action: str = "pause",
) -> dict:
    return {
        "global_cap_usd": 1.0,
        "used_usd": 1.0 if global_reached else 0.0,
        "action": action,
        "global_reached": global_reached,
        "exhausted_difficulties": list(exhausted),
    }


def _guard(monkeypatch, state: dict | None, failing: bool = False) -> BudgetGuard:
    session = object()  # 仅透传给被 monkeypatch 的读取函数

    def fake_execution_budget(_session, owner_id):
        assert owner_id == "owner-1"
        if failing:
            raise RuntimeError("db down")
        return state

    monkeypatch.setattr(
        "src.tasks.budget_guard.CostService.execution_budget", fake_execution_budget
    )
    return BudgetGuard(lambda: contextlib.nullcontext(session), "owner-1")


def test_global_reached_pauses(monkeypatch):
    guard = _guard(monkeypatch, _state(global_reached=True))
    assert guard.should_pause() is True


def test_downgrade_action_still_pauses_for_non_evaluation_loops(monkeypatch):
    # 对实验/基准/A/B 不存在保语义的降级：downgrade 同样停止派发（暂停）。
    guard = _guard(monkeypatch, _state(global_reached=True, action="downgrade"))
    assert guard.should_pause() is True


def test_within_budget_continues(monkeypatch):
    guard = _guard(monkeypatch, _state())
    assert guard.should_pause() is False


def test_difficulty_exhaustion_alone_does_not_pause(monkeypatch):
    # 按难度暂停需要 runner 暴露下一单元难度；v1 只以全局预算触发，
    # 难度用量仍进入 last_state 供统计与预警使用。
    guard = _guard(monkeypatch, _state(exhausted=("easy",)))
    assert guard.should_pause() is False
    assert guard.last_state is not None
    assert guard.last_state["exhausted_difficulties"] == ["easy"]


def test_no_budget_continues(monkeypatch):
    guard = _guard(monkeypatch, None)
    assert guard.should_pause() is False
    assert guard.last_state is None


def test_read_failure_continues_and_never_raises(monkeypatch):
    guard = _guard(monkeypatch, None, failing=True)
    assert guard.should_pause() is False
    assert guard.last_state is None
