"""A/B prompt testing."""

from __future__ import annotations

import csv
import json
import math
import random
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.checkpoints import UnitCheckpoint, write_checkpoint
from src.harness import AlgorithmHarness
from src.llm_client import LLMClient, SpendObserver
from src.models import HarnessConfig, LLMConfig, Problem, SandboxConfig, StrategyConfig
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.task_service import TaskService
from src.utils.pricing import PricingManager
from src.utils.secrets import redact_sensitive_data

REPORT_SCHEMA_VERSION = "1.1"


class PromptVariant(BaseModel):
    id: str = Field(..., min_length=1)
    description: str = ""
    system_prompt: str | None = None
    prefix: str = ""
    suffix: str = ""


class ABTestConfig(BaseModel):
    name: str | None = None
    dataset_path: str
    output_dir: str = "./results/ab-tests"
    model: LLMConfig
    strategy: StrategyConfig
    prompt_variants: list[PromptVariant] = Field(..., min_length=2, max_length=2)
    baseline_id: str | None = None
    seed: int = 42
    max_workers: int = Field(1, ge=1, le=20)
    sandbox_config: SandboxConfig = Field(default_factory=SandboxConfig)
    problem_filters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_variants(self) -> ABTestConfig:
        ids = [variant.id for variant in self.prompt_variants]
        if len(set(ids)) != 2:
            raise ValueError("prompt_variants must contain exactly two unique IDs")
        if self.baseline_id is not None and self.baseline_id not in ids:
            raise ValueError("baseline_id must match one prompt variant ID")
        return self

    @property
    def baseline(self) -> PromptVariant:
        return next(
            variant
            for variant in self.prompt_variants
            if variant.id == (self.baseline_id or self.prompt_variants[0].id)
        )

    @property
    def treatment(self) -> PromptVariant:
        return next(variant for variant in self.prompt_variants if variant.id != self.baseline.id)

    def redacted_dict(self) -> dict[str, Any]:
        return redact_sensitive_data(self.model_dump(mode="json"))  # type: ignore[no-any-return]


class PromptVariantClient:
    def __init__(self, inner: LLMClient, variant: PromptVariant):
        self.inner = inner
        self.config = inner.config
        self.variant = variant

    def generate(self, prompt: str, *, system_prompt: str | None = None, **kwargs: Any) -> Any:
        return self.inner.generate(
            f"{self.variant.prefix}{prompt}{self.variant.suffix}",
            system_prompt=self.variant.system_prompt or system_prompt,
            **kwargs,
        )


def stratified_assign(
    problems: list[Problem], variants: list[PromptVariant], seed: int
) -> dict[str, str]:
    if len(variants) != 2:
        raise ValueError("A/B tests require exactly two variants")
    rng = random.Random(seed)
    groups: dict[tuple[str, tuple[str, ...]], list[Problem]] = defaultdict(list)
    for problem in problems:
        groups[(problem.difficulty, tuple(sorted(problem.tags)))].append(problem)
    assignment: dict[str, str] = {}
    next_extra_variant = 0
    for key in sorted(groups):
        items = list(groups[key])
        rng.shuffle(items)
        start_variant = 0
        if len(items) % 2:
            start_variant = next_extra_variant
            next_extra_variant = 1 - next_extra_variant
        for index, problem in enumerate(items, start=start_variant):
            assignment[problem.problem_id] = variants[index % 2].id
    return assignment


def _proportion_ci(
    success_a: int, total_a: int, success_b: int, total_b: int
) -> dict[str, float | None]:
    if not total_a or not total_b:
        return {"difference": None, "lower": None, "upper": None}
    p_a = success_a / total_a
    p_b = success_b / total_b
    difference = p_b - p_a
    standard_error = math.sqrt(p_a * (1 - p_a) / total_a + p_b * (1 - p_b) / total_b)
    return {
        "difference": difference,
        "lower": difference - 1.96 * standard_error,
        "upper": difference + 1.96 * standard_error,
    }


def _statistical_tests(success_a: list[int], success_b: list[int]) -> dict[str, Any]:
    unavailable = {"categorical_test": "unavailable", "p_value": None, "welch_t_p_value": None}
    if not success_a or not success_b:
        return unavailable
    passed_a, passed_b = sum(success_a), sum(success_b)
    failed_a, failed_b = len(success_a) - passed_a, len(success_b) - passed_b
    if not (passed_a + passed_b and failed_a + failed_b):
        return unavailable
    table = [
        [passed_a, failed_a],
        [passed_b, failed_b],
    ]
    try:
        from scipy import stats

        _, p_value, _, expected = stats.chi2_contingency(table, correction=False)
        if min(min(row) for row in expected) < 5:
            _, p_value = stats.fisher_exact(table)
            test = "fisher_exact"
        else:
            test = "chi_square"
        welch_p = None
        if min(len(success_a), len(success_b)) >= 2 and (
            (passed_a and failed_a) or (passed_b and failed_b)
        ):
            _, p = stats.ttest_ind(success_a, success_b, equal_var=False)
            if math.isfinite(float(p)):
                welch_p = float(p)
        return {
            "categorical_test": test,
            "p_value": float(p_value),
            "welch_t_p_value": welch_p,
        }
    except (ImportError, ValueError, ZeroDivisionError):
        return unavailable


class ABTestRunner:
    def __init__(
        self,
        config: ABTestConfig,
        *,
        client_factory: Callable[[LLMConfig], Any] = LLMClient,
        sandbox_factory: Callable[[SandboxConfig], Any] = SandboxExecutor,
    ):
        self.config = config
        self.client_factory = client_factory
        self.sandbox_factory = sandbox_factory
        self.should_stop: Callable[[], bool] = lambda: False
        self.paused = False
        self.checkpoint_dir: Path | None = None
        self._checkpoint: UnitCheckpoint | None = None
        self.on_problem: Callable[[int, int, str], None] | None = None
        self._completed = 0
        self._total = 0
        self._progress_lock = threading.Lock()
        self.pricing_manager: PricingManager | None = None
        self.on_spend: SpendObserver | None = None
        self.before_generate: Callable[[], None] | None = None

    def run(self) -> Path:
        problems = ProblemLoader().load(self.config.dataset_path)
        if self.config.problem_filters:
            problems = ProblemLoader().filter_problems(problems, **self.config.problem_filters)
        assignment = stratified_assign(problems, self.config.prompt_variants, self.config.seed)
        if len(assignment) != len(problems):
            raise ValueError("A/B test requires unique problem IDs after filtering")
        if len(set(assignment.values())) != 2:
            raise ValueError(
                "A/B test requires at least one problem in each variant after filtering"
            )
        output = self._create_output_dir()
        if self.checkpoint_dir is not None:
            checkpoint_config = self.config.redacted_dict()
            checkpoint_config.pop("dataset_path", None)
            self._checkpoint = UnitCheckpoint(
                output / "units",
                TaskService.config_fingerprint(
                    {
                        "config": checkpoint_config,
                        "problems": [problem.model_dump(mode="json") for problem in problems],
                    }
                ),
            )
        self._total = len(problems)
        assignments = {
            problem.problem_id: {
                "variant": assignment[problem.problem_id],
                "difficulty": problem.difficulty,
                "tags": list(problem.tags),
            }
            for problem in problems
        }
        self._completed = (
            sum(
                self._checkpoint.get(json.dumps([assignment[p.problem_id], p.problem_id]))
                is not None
                for p in problems
            )
            if self._checkpoint is not None
            else 0
        )
        rows = []
        for variant in self.config.prompt_variants:
            rows.extend(
                self._run_variant(
                    variant, [p for p in problems if assignment[p.problem_id] == variant.id]
                )
            )
        if self.should_stop():
            self.paused = True
            return output
        report = self._build_report(rows, assignments, output)
        write_checkpoint(output / "ab_test.json", report)
        self._write_csv(output / "results.csv", rows)
        (output / "REPORT.md").write_text(self._markdown(report), encoding="utf-8")
        return output

    def _run_variant(self, variant: PromptVariant, problems: list[Problem]) -> list[dict[str, Any]]:
        def run(problem: Problem) -> dict[str, Any] | None:
            key = json.dumps([variant.id, problem.problem_id])
            saved = self._checkpoint.get(key) if self._checkpoint is not None else None
            if saved is not None:
                return saved
            if self.should_stop():
                self.paused = True
                return None
            sandbox = self.sandbox_factory(self.config.sandbox_config)
            ok, detail = sandbox.health_check()
            if not ok:
                raise RuntimeError(f"Sandbox preflight failed: {detail}")
            base_client = self.client_factory(self.config.model)
            if self.pricing_manager is not None:
                base_client.pricing_manager = self.pricing_manager
            base_client.before_generate = self.before_generate
            if self.on_spend is not None:
                base_client.on_response = lambda event_id, response, cached: self.on_spend(
                    event_id,
                    response,
                    cached,
                    {
                        "model": self.config.model.model,
                        "strategy": self.config.strategy.name,
                        "problem_id": problem.problem_id,
                        "difficulty": problem.difficulty,
                    },
                )
            client = PromptVariantClient(base_client, variant)
            strategy = AlgorithmHarness.STRATEGY_MAP[self.config.strategy.name](
                self.config.strategy,
                client,  # type: ignore[arg-type]
                sandbox,  # type: ignore[abstract]
            )
            harness = AlgorithmHarness(
                HarnessConfig(
                    llm_config=self.config.model,
                    sandbox_config=self.config.sandbox_config,
                    dataset_path=self.config.dataset_path,
                    strategies=[self.config.strategy],
                )
            )
            started = time.perf_counter()
            result = harness._execute_problem(self.config.strategy, problem, strategy, sandbox)
            row = {
                "variant": variant.id,
                "problem_id": problem.problem_id,
                "difficulty": problem.difficulty,
                "tags": list(problem.tags),
                "status": result.status,
                "success": result.status == "success",
                "formal_evaluable": result.formal_evaluable,
                "formal_passed": bool(result.hidden_result and result.hidden_result.all_passed),
                "sample_passed": bool(result.final_result and result.final_result.all_passed),
                "failure_category": result.failure_category,
                "total_tokens": result.total_tokens,
                "elapsed_seconds": time.perf_counter() - started,
                "iterations": len(result.iterations),
                "error_message": result.error_message,
            }
            if self._checkpoint is not None:
                self._checkpoint.put(key, redact_sensitive_data(row))
            self._report_problem(variant.id, problem.problem_id)
            return row

        if self.config.max_workers == 1 or len(problems) < 2:
            return [result for problem in problems if (result := run(problem)) is not None]
        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(problems))) as pool:
            return [result for result in pool.map(run, problems) if result is not None]

    def _report_problem(self, variant: str, problem_id: str) -> None:
        with self._progress_lock:
            self._completed += 1
            if self.on_problem is not None:
                self.on_problem(self._completed, self._total, f"{variant}/{problem_id}")

    def _build_report(
        self, rows: list[dict[str, Any]], assignments: dict[str, Any], output: Path
    ) -> dict[str, Any]:
        baseline = self.config.baseline.id
        treatment = self.config.treatment.id
        by_variant = {
            variant.id: [row for row in rows if row["variant"] == variant.id]
            for variant in self.config.prompt_variants
        }
        pass_statistics = self._pass_statistics(by_variant[baseline], by_variant[treatment])
        grouped = self._grouped_rates(rows)
        return redact_sensitive_data(  # type: ignore[no-any-return]
            {
                "schema_version": REPORT_SCHEMA_VERSION,
                "name": self.config.name or "ab-test",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "output_dir": str(output),
                "seed": self.config.seed,
                "model": self.config.model.redacted_dict(),
                "strategy": self.config.strategy.model_dump(mode="json"),
                "variants": [
                    variant.model_dump(mode="json") for variant in self.config.prompt_variants
                ],
                "baseline_id": baseline,
                "treatment_id": treatment,
                "assignments": assignments,
                "balance": self._balance(assignments),
                "comparison": {
                    **pass_statistics,
                    "elapsed_seconds": {
                        key: sum(row["elapsed_seconds"] for row in value)
                        for key, value in by_variant.items()
                    },
                    "tokens": {
                        key: sum(row["total_tokens"] for row in value)
                        for key, value in by_variant.items()
                    },
                    "failure_categories": {
                        key: self._failure_counts(value) for key, value in by_variant.items()
                    },
                },
                "by_difficulty": grouped["difficulty"],
                "by_tag": grouped["tag"],
                "recommendation": self._recommendation(
                    pass_statistics["statistics"], pass_statistics["sample"]["ci95"]
                ),
                "rows": rows,
            }
        )

    @staticmethod
    def _pass_statistics(
        baseline: list[dict[str, Any]], treatment: list[dict[str, Any]]
    ) -> dict[str, Any]:
        sample_a = [int(row["sample_passed"]) for row in baseline]
        sample_b = [int(row["sample_passed"]) for row in treatment]
        formal_a = [int(row["formal_passed"]) for row in baseline if row["formal_evaluable"]]
        formal_b = [int(row["formal_passed"]) for row in treatment if row["formal_evaluable"]]
        return {
            "sample": ABTestRunner._pass_comparison(sample_a, sample_b),
            "formal": ABTestRunner._pass_comparison(formal_a, formal_b),
            "statistics": _statistical_tests(sample_a, sample_b),
            "formal_statistics": _statistical_tests(formal_a, formal_b),
        }

    @staticmethod
    def _pass_comparison(baseline: list[int], treatment: list[int]) -> dict[str, Any]:
        passed_a, passed_b = sum(baseline), sum(treatment)
        return {
            "baseline": passed_a / len(baseline) if baseline else None,
            "treatment": passed_b / len(treatment) if treatment else None,
            "ci95": _proportion_ci(passed_a, len(baseline), passed_b, len(treatment)),
        }

    @classmethod
    def upgrade_legacy_report(cls, report: dict[str, Any]) -> None:
        """Recompute a 1.0 report in memory using its original per-problem outcomes."""
        if report.get("schema_version") != "1.0":
            return
        rows = report.get("rows")
        comparison = report.get("comparison")
        baseline, treatment = report.get("baseline_id"), report.get("treatment_id")
        error = "Legacy A/B report has incomplete outcomes; rerun the A/B test"
        if (
            not isinstance(rows, list)
            or not isinstance(comparison, dict)
            or not isinstance(baseline, str)
            or not isinstance(treatment, str)
            or baseline == treatment
        ):
            raise ValueError(error)
        by_variant: dict[str, list[dict[str, Any]]] = {baseline: [], treatment: []}
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("variant") not in (baseline, treatment)
                or not isinstance(row.get("sample_passed"), bool)
                or not isinstance(row.get("formal_evaluable"), bool)
                or (row["formal_evaluable"] and not isinstance(row.get("formal_passed"), bool))
            ):
                raise ValueError(error)
            by_variant[row["variant"]].append(row)
        if not by_variant[baseline] or not by_variant[treatment]:
            raise ValueError(error)
        pass_statistics = cls._pass_statistics(by_variant[baseline], by_variant[treatment])
        comparison.update(pass_statistics)
        report["recommendation"] = cls._recommendation(
            pass_statistics["statistics"], pass_statistics["sample"]["ci95"]
        )
        report["schema_version"] = REPORT_SCHEMA_VERSION

    @staticmethod
    def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            if row["failure_category"]:
                counts[row["failure_category"]] += 1
        return dict(counts)

    @staticmethod
    def _balance(assignments: dict[str, Any]) -> dict[str, dict[str, int]]:
        strata: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for item in assignments.values():
            strata[str((item["difficulty"], tuple(sorted(item["tags"]))))][item["variant"]] += 1
        return {key: dict(value) for key, value in strata.items()}

    @staticmethod
    def _grouped_rates(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
        grouped: dict[str, dict[str, list[int]]] = {
            "difficulty": defaultdict(lambda: [0, 0]),
            "tag": defaultdict(lambda: [0, 0]),
        }
        for row in rows:
            grouped["difficulty"][row["difficulty"]][0] += int(row["success"])
            grouped["difficulty"][row["difficulty"]][1] += 1
            for tag in row["tags"] or ["unknown"]:
                grouped["tag"][tag][0] += int(row["success"])
                grouped["tag"][tag][1] += 1
        return {
            kind: {
                key: {
                    "success": value[0],
                    "total": value[1],
                    "rate": value[0] / value[1] if value[1] else None,
                }
                for key, value in groups.items()
            }
            for kind, groups in grouped.items()
        }

    @staticmethod
    def _recommendation(stats: dict[str, Any], sample_ci: dict[str, float | None]) -> str:
        p_value = stats.get("p_value")
        difference = sample_ci.get("difference")
        if p_value is not None and p_value < 0.05 and difference is not None:
            winner = "treatment" if difference > 0 else "baseline"
            return (
                f"{winner} variant shows a statistically significant sample success-rate "
                f"difference (p={p_value:.4g}). Verify on a fresh split before adoption."
            )
        return "No statistically significant sample difference detected; collect more stratified samples before choosing a winner."

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        fields = [
            "variant",
            "problem_id",
            "difficulty",
            "status",
            "success",
            "formal_evaluable",
            "formal_passed",
            "sample_passed",
            "failure_category",
            "total_tokens",
            "elapsed_seconds",
            "iterations",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({field: row.get(field) for field in fields} for row in rows)

    @staticmethod
    def _markdown(report: dict[str, Any]) -> str:
        def format_rate(value: float | None) -> str:
            return "—" if value is None else f"{value * 100:g}%"

        comparison = report["comparison"]
        lines = [
            f"# A/B Test: {report['name']}",
            "",
            f"Baseline: `{report['baseline_id']}`",
            f"Treatment: `{report['treatment_id']}`",
            f"Seed: `{report['seed']}`",
            f"Report schema: `{report['schema_version']}`",
            "",
            "| Variant | Sample rate | Formal rate | Tokens | Seconds |",
            "|---|---:|---:|---:|---:|",
        ]
        for variant in report["variants"]:
            variant_id = variant["id"]
            role = "baseline" if variant_id == report["baseline_id"] else "treatment"
            lines.append(
                f"| {variant_id} | {format_rate(comparison['sample'][role])} | "
                f"{format_rate(comparison['formal'][role])} | {comparison['tokens'][variant_id]} | "
                f"{comparison['elapsed_seconds'][variant_id]:.3f} |"
            )
        lines.extend(
            [
                "",
                f"Sample test: {comparison['statistics']['categorical_test']} "
                f"(p-value: {comparison['statistics']['p_value']}, "
                f"Welch t p-value: {comparison['statistics']['welch_t_p_value']})",
                f"Formal test: {comparison['formal_statistics']['categorical_test']} "
                f"(p-value: {comparison['formal_statistics']['p_value']}, "
                f"Welch t p-value: {comparison['formal_statistics']['welch_t_p_value']})",
                "",
                report["recommendation"],
                "",
            ]
        )
        return "\n".join(lines)

    def _create_output_dir(self) -> Path:
        if self.checkpoint_dir is not None:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            return self.checkpoint_dir
        base = Path(self.config.output_dir)
        name = f"ab-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        output = base / name
        suffix = 1
        while output.exists():
            suffix += 1
            output = base / f"{name}-{suffix}"
        output.mkdir(parents=True)
        return output
