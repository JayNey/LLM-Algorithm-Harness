"""Fixed-budget experiments over model, strategy, problem, and repetition."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    Problem,
    SandboxConfig,
    StrategyConfig,
)
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.task_service import TaskService, TaskUnit
from src.utils.secrets import redact_sensitive_data, redact_sensitive_text


class GenerationBudget(BaseModel):
    """Equal per-problem limits applied to every model/strategy pair."""

    max_calls: int = Field(3, ge=1)
    max_total_tokens: int | None = Field(None, ge=1)
    max_elapsed_seconds: float | None = Field(None, gt=0)


class ModelPrice(BaseModel):
    """Explicit USD rates per 1,000 input and output tokens."""

    input_per_1k_usd: float = Field(..., ge=0)
    output_per_1k_usd: float = Field(..., ge=0)
    source: str = Field(..., min_length=1)
    as_of: date


class ExperimentModel(BaseModel):
    name: str = Field(..., min_length=1)
    llm_config: LLMConfig
    price: ModelPrice | None = None


class ExperimentConfig(BaseModel):
    dataset_path: str
    output_dir: str = "./results"
    models: list[ExperimentModel] = Field(..., min_length=1)
    strategies: list[StrategyConfig] = Field(..., min_length=1)
    sandbox_config: SandboxConfig = Field(default_factory=SandboxConfig)
    problem_filters: dict[str, Any] | None = None
    repetitions: int = Field(1, ge=1, le=20)
    max_workers: int = Field(1, ge=1, le=20)
    budget: GenerationBudget = Field(default_factory=GenerationBudget)

    @model_validator(mode="after")
    def distinct_names(self):
        for names in ([model.name for model in self.models], [item.name for item in self.strategies]):
            if len(names) != len(set(names)):
                raise ValueError("Model and strategy names must be unique")
        unknown = {item.name for item in self.strategies} - set(AlgorithmHarness.STRATEGY_MAP)
        if unknown:
            raise ValueError(f"Unsupported strategies: {', '.join(sorted(unknown))}")
        return self

    def fingerprint(self) -> str:
        """Canonical configuration hash with credential changes represented safely."""
        payload = self.model_dump(mode="json")
        for saved, model in zip(payload["models"], self.models, strict=True):
            configured_key = model.llm_config.api_key
            secret = (
                configured_key.get_secret_value()
                if hasattr(configured_key, "get_secret_value")
                else str(configured_key)
            )
            if secret.startswith("env:"):
                secret = os.getenv(secret[4:], "")
            elif secret.startswith("${") and secret.endswith("}"):
                secret = os.getenv(secret[2:-1], "")
            saved["api_key_fingerprint"] = hashlib.sha256(secret.encode()).hexdigest()
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class BudgetExceeded(RuntimeError):
    """Raised before an additional provider request would exceed a budget."""


class BudgetedLLMClient:
    """Track calls and known usage; reject subsequent calls at the limit."""

    def __init__(self, client: LLMClient, budget: GenerationBudget):
        self.client = client
        self.config = client.config
        self.budget = budget
        self.started = time.monotonic()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reported_total_tokens = 0
        self.reasoning_tokens = 0
        self.usage_unknown = False
        self.denied_reason: str | None = None

    @property
    def total_tokens(self) -> int:
        return max(
            self.reported_total_tokens,
            self.prompt_tokens + self.completion_tokens,
            self.prompt_tokens + self.reasoning_tokens,
        )

    def generate(self, prompt: str, **kwargs):
        elapsed = time.monotonic() - self.started
        if self.calls >= self.budget.max_calls:
            self.denied_reason = "call_budget_exhausted"
        elif self.budget.max_elapsed_seconds is not None and elapsed >= self.budget.max_elapsed_seconds:
            self.denied_reason = "time_budget_exhausted"
        elif self.budget.max_total_tokens is not None and self.usage_unknown:
            self.denied_reason = "token_usage_unknown"
        elif self.budget.max_total_tokens is not None and self.total_tokens >= self.budget.max_total_tokens:
            self.denied_reason = "token_budget_exhausted"
        if self.denied_reason:
            raise BudgetExceeded(self.denied_reason)

        # A provider knows its output ceiling, but input and reasoning usage
        # are only known after the response. Token limits are therefore a
        # pre-call gate plus a recorded post-call overshoot, not a hard cap.
        if self.budget.max_total_tokens is not None:
            remaining = self.budget.max_total_tokens - self.total_tokens
            configured = kwargs.get("max_tokens") or self.config.max_tokens
            kwargs["max_tokens"] = min(configured, remaining)
        self.calls += 1
        try:
            response = self.client.generate(prompt, **kwargs)
        except Exception:
            self.usage_unknown = True
            raise
        if response.usage_missing:
            self.usage_unknown = True
        else:
            self.prompt_tokens += response.usage.prompt_tokens
            self.completion_tokens += response.usage.completion_tokens
            self.reported_total_tokens += response.usage.total_tokens
            self.reasoning_tokens += response.reasoning_tokens or 0
        return response

    def snapshot(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started
        limit = self.budget.max_total_tokens
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens_reported": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "unattributed_tokens": max(
                0, self.total_tokens - self.prompt_tokens - self.completion_tokens
            ),
            "usage_known": not self.usage_unknown,
            "elapsed_seconds": elapsed,
            "stop_reason": self.denied_reason,
            "token_limit_mode": "post_response_observed" if limit is not None else "none",
            "token_limit_overshot": bool(limit is not None and self.total_tokens > limit),
            "time_limit_overshot": bool(
                self.budget.max_elapsed_seconds is not None
                and elapsed > self.budget.max_elapsed_seconds
            ),
        }


def _code_version() -> str:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
        return f"{commit}-dirty" if dirty else commit
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class ExperimentRunner:
    """Execute and export repeatable experiments using the task service."""

    def __init__(
        self,
        config: ExperimentConfig,
        *,
        client_factory: Callable[[LLMConfig], Any] = LLMClient,
        sandbox_factory: Callable[[SandboxConfig], Any] = SandboxExecutor,
    ):
        self.config = config
        self.client_factory = client_factory
        self.sandbox_factory = sandbox_factory
        self.service = TaskService(Path(config.output_dir) / "experiments" / "tasks")

    def run(self, *, run_id: str | None = None, resume: bool = False) -> dict[str, Any]:
        problems = ProblemLoader().load(self.config.dataset_path)
        if self.config.problem_filters:
            problems = ProblemLoader().filter_problems(problems, **self.config.problem_filters)
        if not problems:
            raise ValueError("Experiment requires at least one problem")
        problem_map = {problem.problem_id: problem for problem in problems}
        if len(problem_map) != len(problems):
            raise ValueError("Experiment problem IDs must be unique")

        config_hash = self.config.fingerprint()
        dataset_hash = self.service.dataset_fingerprint(self.config.dataset_path)
        if resume:
            if not run_id:
                raise ValueError("resume requires run_id")
            task = self.service.get(run_id)
        else:
            units = [
                TaskUnit(
                    unit_id=f"{model.name}:{strategy.name}:{problem.problem_id}:{repeat}",
                    model_id=model.name,
                    strategy=strategy.name,
                    problem_id=problem.problem_id,
                    repeat_index=repeat,
                )
                for model in self.config.models
                for strategy in self.config.strategies
                for problem in problems
                for repeat in range(self.config.repetitions)
            ]
            if len({unit.unit_id for unit in units}) != len(units):
                raise ValueError("Experiment unit IDs must be unique")
            task = self.service.create(
                units=units,
                config_fingerprint=config_hash,
                dataset_fingerprint=dataset_hash,
                run_id=run_id,
            )

        sandbox = self.sandbox_factory(self.config.sandbox_config)
        ok, detail = sandbox.health_check()
        if not ok:
            self.service.fail(task.run_id, redact_sensitive_text(detail or "Sandbox unavailable"))
            raise RuntimeError(f"Sandbox preflight failed: {detail}")
        model_map = {model.name: model for model in self.config.models}
        strategy_map = {strategy.name: strategy for strategy in self.config.strategies}

        def worker(unit: TaskUnit) -> dict[str, Any]:
            model = model_map[unit.model_id]
            strategy_config = strategy_map[unit.strategy]
            problem = problem_map[unit.problem_id]
            budgeted = BudgetedLLMClient(self.client_factory(model.llm_config), self.config.budget)
            strategy = AlgorithmHarness.STRATEGY_MAP[unit.strategy](strategy_config, budgeted, sandbox)
            harness = AlgorithmHarness(
                HarnessConfig(
                    llm_config=model.llm_config,
                    sandbox_config=self.config.sandbox_config,
                    dataset_path=self.config.dataset_path,
                    strategies=[strategy_config],
                    output_dir=self.config.output_dir,
                )
            )
            result = harness._execute_problem(strategy_config, problem, strategy, sandbox)
            usage = budgeted.snapshot()
            if budgeted.denied_reason:
                result.status = "budget_exhausted"
                result.failure_category = "budget_exhausted"
                result.error_message = budgeted.denied_reason
            return {
                "execution": result.model_dump(mode="json"),
                "budget": usage,
                "model": model.name,
                "strategy": unit.strategy,
                "problem_id": unit.problem_id,
                "repeat_index": unit.repeat_index,
            }

        finished = self.service.run(
            task.run_id,
            worker,
            max_workers=self.config.max_workers,
            config_fingerprint=config_hash,
            dataset_fingerprint=dataset_hash,
            resume=resume,
        )
        report = self._report(finished, problem_map, model_map, config_hash, dataset_hash)
        self._write_report(report)
        return report

    def _report(
        self,
        task,
        problems: dict[str, Problem],
        models: dict[str, ExperimentModel],
        config_hash: str,
        dataset_hash: str,
    ) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for unit in task.units:
            if unit.result:
                record = dict(unit.result)
                execution = ExecutionResult.model_validate(record["execution"])
                model = models[unit.model_id]
                price = model.price
                budget = record["budget"]
                cost = None
                if price is not None and budget["usage_known"] and not budget["unattributed_tokens"]:
                    cost = (
                        budget["prompt_tokens"] * price.input_per_1k_usd
                        + budget["completion_tokens"] * price.output_per_1k_usd
                    ) / 1000
                record["cost_usd"] = cost
                record["price_source"] = price.source if price else None
                record["price_as_of"] = price.as_of.isoformat() if price else None
                # The normal client may attach a fallback estimate for an
                # unknown model. Experiment reports use only the explicitly
                # configured price so nested traces cannot imply a false cost.
                for trace in record["execution"].get("llm_traces", []):
                    trace_cost = None
                    if (
                        price is not None
                        and not trace.get("usage_missing", True)
                        and not budget["unattributed_tokens"]
                    ):
                        trace_cost = (
                            trace.get("prompt_tokens", 0) * price.input_per_1k_usd
                            + trace.get("completion_tokens", 0) * price.output_per_1k_usd
                        ) / 1000
                    trace["pricing_metadata"] = {
                        "source": price.source if price else "unknown",
                        "as_of": price.as_of.isoformat() if price else None,
                        "total_cost": trace_cost,
                    }
                record["sample_passed"] = bool(
                    execution.final_result and execution.final_result.all_passed
                )
                record["sample_evaluable"] = bool(
                    problems[unit.problem_id].public_test_cases
                    or problems[unit.problem_id].feedback_test_cases
                )
                record["formal_evaluable"] = execution.formal_evaluable
                record["formal_passed"] = bool(
                    execution.hidden_result and execution.hidden_result.all_passed
                )
                record["repaired"] = self._repaired(execution)
                record["repair_eligible"] = self._repair_eligible(execution)
                record["difficulty"] = problems[unit.problem_id].difficulty
                record["tags"] = problems[unit.problem_id].tags
                record["failure_category"] = execution.failure_category
                record["status"] = execution.status
            else:
                record = {
                    "model": unit.model_id, "strategy": unit.strategy,
                    "problem_id": unit.problem_id, "repeat_index": unit.repeat_index,
                    "status": unit.status, "failure_category": "system_error",
                    "difficulty": problems[unit.problem_id].difficulty,
                    "tags": problems[unit.problem_id].tags,
                    "sample_passed": False,
                    "sample_evaluable": bool(
                        problems[unit.problem_id].public_test_cases
                        or problems[unit.problem_id].feedback_test_cases
                    ),
                    "formal_evaluable": problems[unit.problem_id].formal_evaluable,
                    "formal_passed": False, "repair_eligible": False, "repaired": False,
                    "budget": None, "cost_usd": None, "price_source": None,
                    "price_as_of": None, "error": unit.error,
                }
            records.append(record)

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            groups[f"{record['model']}:{record['strategy']}"].append(record)
        summaries = {key: self._summarize(items) for key, items in groups.items()}
        return redact_sensitive_data({
            "run_id": task.run_id,
            "state": task.state,
            "created_at": task.created_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_fingerprint": config_hash,
            "dataset_fingerprint": dataset_hash,
            "code_version": _code_version(),
            "budget": self.config.budget.model_dump(mode="json"),
            "effective_models": [
                {"name": model.name, "config": model.llm_config.redacted_dict(),
                 "price": model.price.model_dump(mode="json") if model.price else None}
                for model in self.config.models
            ],
            "strategies": [strategy.model_dump(mode="json") for strategy in self.config.strategies],
            "repetitions": self.config.repetitions,
            "summaries": summaries,
            "records": records,
            "uncertainty_note": "Repeated remote generations may differ; this metadata does not claim bitwise reproducibility.",
        })

    @staticmethod
    def _repair_eligible(execution: ExecutionResult) -> bool:
        return bool(
            len(execution.iterations) >= 2
            and execution.iterations[0].sandbox_result is not None
            and not execution.iterations[0].sandbox_result.all_passed
        )

    @classmethod
    def _repaired(cls, execution: ExecutionResult) -> bool:
        return cls._repair_eligible(execution) and any(
            it.sandbox_result is not None and it.sandbox_result.all_passed
            for it in execution.iterations[1:]
        )

    @staticmethod
    def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        formal_count = sum(bool(item["formal_evaluable"]) for item in items)
        costs = [item["cost_usd"] for item in items]
        budgets = [item["budget"] for item in items if item["budget"]]
        def empty_breakdown() -> dict[str, Any]:
            return {"total": 0, "formal_passed": 0, "sample_evaluable": 0,
                    "sample_passed": 0,
                    "calls": 0, "known_tokens": 0, "elapsed_seconds": 0.0}

        by_difficulty: dict[str, dict[str, Any]] = defaultdict(empty_breakdown)
        by_tag: dict[str, dict[str, Any]] = defaultdict(empty_breakdown)
        for item in items:
            dimensions = [by_difficulty[item["difficulty"]]] + [by_tag[tag] for tag in item["tags"]]
            for bucket in dimensions:
                bucket["total"] += 1
                bucket["formal_passed"] += int(item["formal_passed"])
                bucket["sample_evaluable"] += int(item["sample_evaluable"])
                bucket["sample_passed"] += int(item["sample_passed"])
                if item["budget"]:
                    bucket["calls"] += item["budget"]["calls"]
                    bucket["known_tokens"] += item["budget"]["total_tokens"]
                    bucket["elapsed_seconds"] += item["budget"]["elapsed_seconds"]
        repeats: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            repeats[item["repeat_index"]].append(item)
        repeat_rates = [
            sum(entry["formal_passed"] for entry in group) / sum(entry["formal_evaluable"] for entry in group)
            for group in repeats.values() if any(entry["formal_evaluable"] for entry in group)
        ]
        repair_eligible = sum(item["repair_eligible"] for item in items)
        sample_count = sum(item["sample_evaluable"] for item in items)
        return {
            "total": count,
            "formal_evaluable": formal_count,
            "formal_passed": sum(item["formal_passed"] for item in items),
            "formal_pass_rate": sum(item["formal_passed"] for item in items) / formal_count if formal_count else None,
            "sample_passed": sum(item["sample_passed"] for item in items),
            "sample_evaluable": sample_count,
            "sample_pass_rate": sum(item["sample_passed"] for item in items) / sample_count if sample_count else None,
            "failure_counts": dict(Counter(item["failure_category"] or "none" for item in items)),
            "repair_eligible": repair_eligible,
            "repaired": sum(item["repaired"] for item in items),
            "repair_rate": sum(item["repaired"] for item in items) / repair_eligible if repair_eligible else None,
            "calls": sum(budget["calls"] for budget in budgets),
            "prompt_tokens_known": sum(budget["prompt_tokens"] for budget in budgets),
            "completion_tokens_known": sum(budget["completion_tokens"] for budget in budgets),
                    "reasoning_tokens_reported": sum(budget["reasoning_tokens_reported"] for budget in budgets),
            "usage_known": len(budgets) == count and all(budget["usage_known"] for budget in budgets),
            "elapsed_seconds": sum(budget["elapsed_seconds"] for budget in budgets),
            "cost_usd": sum(costs) if costs and all(value is not None for value in costs) else None,
            "by_difficulty": dict(by_difficulty),
            "by_tag": dict(by_tag),
            "repeat_formal_rate_range": [min(repeat_rates), max(repeat_rates)] if len(repeat_rates) > 1 else None,
        }

    def _write_report(self, report: dict[str, Any]) -> None:
        target = Path(self.config.output_dir) / "experiments" / report["run_id"]
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        fields = ["model", "strategy", "problem_id", "repeat_index", "status", "failure_category",
                  "difficulty", "sample_evaluable", "sample_passed", "formal_evaluable", "formal_passed", "cost_usd",
                  "price_source", "price_as_of"]
        with (target / "results.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for record in report["records"]:
                writer.writerow({key: record.get(key) for key in fields})
        lines = [f"# Experiment {report['run_id']}", "", f"State: {report['state']}",
                 f"Dataset fingerprint: {report['dataset_fingerprint']}",
                 f"Code version: {report['code_version']}",
                 "", "| Model / strategy | Formal | Sample | Calls | Cost (USD) |", "|---|---:|---:|---:|---:|"]
        for key, summary in report["summaries"].items():
            formal = f"{summary['formal_passed']}/{summary['formal_evaluable']}" if summary["formal_evaluable"] else "unknown"
            sample = f"{summary['sample_passed']}/{summary['sample_evaluable']}" if summary["sample_evaluable"] else "unknown"
            cost = f"{summary['cost_usd']:.6f}" if summary["cost_usd"] is not None else "unknown"
            lines.append(f"| {key} | {formal} | {sample} | {summary['calls']} | {cost} |")
        for model in report["effective_models"]:
            price = model["price"]
            if price:
                lines.append(f"\nPrice for {model['name']}: {price['source']} as of {price['as_of']} "
                             f"(input {price['input_per_1k_usd']}, output {price['output_per_1k_usd']} USD/1K).")
            else:
                lines.append(f"\nPrice for {model['name']}: unknown.")
        for key, summary in report["summaries"].items():
            lines.extend([
                "", f"## {key}",
                f"Known tokens: {summary['prompt_tokens_known']} input, "
                f"{summary['completion_tokens_known']} output "
                f"({summary['reasoning_tokens_reported']} reasoning reported).",
                f"Usage known for all calls: {summary['usage_known']}.",
                f"Elapsed: {summary['elapsed_seconds']:.3f} seconds.",
                f"Repairs: {summary['repaired']}/{summary['repair_eligible']} eligible first failures.",
                f"Failure categories: {json.dumps(summary['failure_counts'], ensure_ascii=False)}.",
                f"By difficulty: {json.dumps(summary['by_difficulty'], ensure_ascii=False)}.",
                f"By tag: {json.dumps(summary['by_tag'], ensure_ascii=False)}.",
            ])
            if summary["repeat_formal_rate_range"]:
                lines.append(f"Observed formal pass-rate range across repetitions: "
                             f"{summary['repeat_formal_rate_range'][0]:.2%}–"
                             f"{summary['repeat_formal_rate_range'][1]:.2%}.")
        lines.extend(["", report["uncertainty_note"], ""])
        (target / "report.md").write_text("\n".join(lines), encoding="utf-8")
