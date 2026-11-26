"""Owner-scoped, immutable Web execution plans. Never expose private snapshots."""

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only, sessionmaker

from api.db.models import Evaluation, EvaluationResult
from src.incremental.fingerprint import (
    compute_execution_fingerprint,
    compute_problem_fingerprint,
    hash_json,
)
from src.models import HarnessConfig, LLMConfig, Problem, SandboxConfig, StrategyConfig

PLAN_VERSION = 1
WEB_EXECUTION_VERSION = 1


def execution_config(llm: LLMConfig, names: list[str]) -> HarnessConfig:
    return HarnessConfig(
        llm_config=llm,
        sandbox_config=SandboxConfig(),
        dataset_path="db://evaluations",
        strategies=[StrategyConfig(name=name) for name in names],
        budget_cap_usd=None,
        enable_quality_analysis=False,
    )


def execution_fingerprint(llm: LLMConfig, strategy: str) -> str:
    return hash_json(
        {
            "web_execution_version": WEB_EXECUTION_VERSION,
            "execution": compute_execution_fingerprint(execution_config(llm, [strategy])),
        }
    )


def reuse_summary(plan: dict | None) -> dict[str, int]:
    units = (plan or {}).get("units", [])
    reused = sum(bool(unit.get("source")) for unit in units)
    return {"total_units": len(units), "reused_units": reused, "new_units": len(units) - reused}


def new_cost(metrics: dict | None) -> float:
    value = metrics or {}
    return float(value.get("new_cost_usd", value.get("cost_usd", 0)) or 0)


def new_cost_unknown(metrics: dict | None) -> bool:
    value = metrics or {}
    return bool(value.get("new_cost_unknown", value.get("cost_unknown", False)))


def validate_plan(evaluation: Evaluation) -> dict[str, Any]:
    plan = evaluation.reuse_plan
    try:
        if not isinstance(plan, dict) or plan["version"] != PLAN_VERSION:
            raise ValueError
        if plan["digest"] != hash_json({k: v for k, v in plan.items() if k != "digest"}):
            raise ValueError
        expected = [
            (name, pid) for name in evaluation.strategy_names for pid in evaluation.problem_ids
        ]
        if [(u["strategy"], u["problem_id"]) for u in plan["units"]] != expected:
            raise ValueError
        if set(plan["problems"]) != set(evaluation.problem_ids):
            raise ValueError
        if (
            plan["model"] != evaluation.model
            or plan["timeout"] != evaluation.effective_generation_timeout
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("Incremental execution plan is missing, damaged or incompatible") from None
    return plan


def build_plan(
    evaluation: Evaluation, factory: sessionmaker[Session], *, auth: Any = None
) -> dict[str, Any]:
    # Lazy import keeps the ordinary service startup independent of worker setup.
    from src.harness import AlgorithmHarness
    from src.tasks.evaluation import _freeze_problem, _resolve_execution_context

    if any(name not in AlgorithmHarness.STRATEGY_MAP for name in evaluation.strategy_names):
        raise ValueError("Unknown evaluation strategy")
    ctx = _resolve_execution_context(evaluation, factory, auth=auth, use_plan=False)
    if ctx.missing_problems:
        raise ValueError("One or more selected problems are unavailable or invalid")
    fingerprints = {
        name: execution_fingerprint(ctx.llm_config, name) for name in evaluation.strategy_names
    }
    problems = {pid: _freeze_problem(ctx, pid) for pid in evaluation.problem_ids}
    problem_fingerprints = {
        pid: compute_problem_fingerprint(problem) for pid, problem in ctx.problem_map.items()
    }
    matches: dict[tuple[str, str], tuple[EvaluationResult, Evaluation]] = {}
    with factory() as db:
        candidates = db.execute(
            select(EvaluationResult, Evaluation)
            .join(Evaluation, Evaluation.id == EvaluationResult.evaluation_id)
            .options(load_only(Evaluation.id, Evaluation.run_id))
            .where(
                Evaluation.user_id == evaluation.user_id,
                Evaluation.status == "completed",
                EvaluationResult.problem_id.in_(evaluation.problem_ids),
                EvaluationResult.strategy_name.in_(evaluation.strategy_names),
            )
            .order_by(
                Evaluation.completed_at.desc(),
                EvaluationResult.created_at.desc(),
                EvaluationResult.id.desc(),
            )
        )
        for row, source in candidates:
            meta = row.metrics or {}
            key = (row.strategy_name, row.problem_id)
            # A dynamic example pool cannot be proven equivalent from configuration.
            if (
                key in matches
                or row.strategy_name == "few_shot_learning"
                or not meta.get("actually_executed")
                or meta.get("reuse_source")
                or meta.get("cost_downgraded")
                or not row.execution_payload
                or row.execution_payload.get("source", "fresh") != "fresh"
                or row.execution_payload.get("evaluation_completed") is False
                or row.status
                in {"pending", "running", "paused", "skipped", "cancelled", "not_evaluable"}
                or meta.get("problem_fingerprint") != problem_fingerprints[row.problem_id]
                or meta.get("execution_fingerprint") != fingerprints[row.strategy_name]
            ):
                continue
            matches[key] = (row, source)
        units = []
        for name in evaluation.strategy_names:
            for pid in evaluation.problem_ids:
                match = matches.get((name, pid))
                unit: dict[str, Any] = {
                    "problem_id": pid,
                    "strategy": name,
                    "problem_fingerprint": problem_fingerprints[pid],
                    "execution_fingerprint": fingerprints[name],
                    "reason": "compatible_history" if match else "no_compatible_history",
                }
                if match:
                    row, source = match
                    unit["source"] = {
                        "evaluation_id": source.id,
                        "run_id": source.run_id or source.web_run_id,
                        "result_id": row.id,
                    }
                    unit["result"] = {
                        "status": row.status,
                        "metrics": deepcopy(row.metrics),
                        "error_message": row.error_message,
                        "execution_payload": deepcopy(row.execution_payload),
                    }
                units.append(unit)
    plan = {
        "version": PLAN_VERSION,
        "model": evaluation.model,
        "timeout": evaluation.effective_generation_timeout,
        "llm": ctx.llm_config.model_dump(mode="json", exclude={"api_key"}),
        "problems": problems,
        "units": units,
    }
    return {**plan, "digest": hash_json(plan)}


def public_preview(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        **reuse_summary(plan),
        "units": [
            {k: unit[k] for k in ("problem_id", "strategy", "reason", "source") if k in unit}
            for unit in plan["units"]
        ],
    }


def restore_problems(plan: dict[str, Any]) -> dict[str, Problem]:
    return {
        pid: Problem.model_validate(snapshot["problem"])
        for pid, snapshot in plan["problems"].items()
    }
