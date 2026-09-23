"""A/B prompt testing."""

from __future__ import annotations

import csv
import json
import math
import random
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
from src.models import HarnessConfig, LLMConfig, Problem, SandboxConfig, StrategyConfig
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.utils.secrets import redact_sensitive_data


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
    def validate_variants(self):
        ids = [variant.id for variant in self.prompt_variants]
        if len(set(ids)) != 2:
            raise ValueError("prompt_variants must contain exactly two unique IDs")
        if self.baseline_id is not None and self.baseline_id not in ids:
            raise ValueError("baseline_id must match one prompt variant ID")
        return self

    @property
    def baseline(self) -> PromptVariant:
        return next(variant for variant in self.prompt_variants if variant.id == (self.baseline_id or self.prompt_variants[0].id))

    @property
    def treatment(self) -> PromptVariant:
        return next(variant for variant in self.prompt_variants if variant.id != self.baseline.id)

    def redacted_dict(self) -> dict[str, Any]:
        return redact_sensitive_data(self.model_dump(mode="json"))


class PromptVariantClient:
    def __init__(self, inner: LLMClient, variant: PromptVariant):
        self.inner = inner
        self.config = inner.config
        self.variant = variant

    def generate(self, prompt: str, *, system_prompt=None, **kwargs):
        return self.inner.generate(
            f"{self.variant.prefix}{prompt}{self.variant.suffix}",
            system_prompt=self.variant.system_prompt or system_prompt,
            **kwargs,
        )


def stratified_assign(problems: list[Problem], variants: list[PromptVariant], seed: int) -> dict[str, str]:
    if len(variants) != 2:
        raise ValueError("A/B tests require exactly two variants")
    rng = random.Random(seed)
    groups: dict[tuple[str, tuple[str, ...]], list[Problem]] = defaultdict(list)
    for problem in problems:
        groups[(problem.difficulty, tuple(sorted(problem.tags)))].append(problem)
    assignment: dict[str, str] = {}
    for key in sorted(groups):
        items = list(groups[key])
        rng.shuffle(items)
        for index, problem in enumerate(items):
            assignment[problem.problem_id] = variants[index % 2].id
    return assignment


def _proportion_ci(success_a: int, total_a: int, success_b: int, total_b: int) -> dict[str, float | None]:
    if not total_a or not total_b:
        return {"difference": None, "lower": None, "upper": None}
    p_a = success_a / total_a
    p_b = success_b / total_b
    difference = p_b - p_a
    standard_error = math.sqrt(p_a * (1 - p_a) / total_a + p_b * (1 - p_b) / total_b)
    return {"difference": difference, "lower": difference - 1.96 * standard_error, "upper": difference + 1.96 * standard_error}


def _statistical_tests(success_a: list[int], success_b: list[int]) -> dict[str, Any]:
    table = [[sum(success_a), len(success_a) - sum(success_a)], [sum(success_b), len(success_b) - sum(success_b)]]
    try:
        from scipy import stats
        expected = stats.chi2_contingency(table, correction=False)[3]
        if min(min(row) for row in expected) < 5:
            _, p_value = stats.fisher_exact(table)
            test = "fisher_exact"
        else:
            _, p_value, _, _ = stats.chi2_contingency(table, correction=False)
            test = "chi_square"
        _, welch_p = stats.ttest_ind(success_a, success_b, equal_var=False)
        return {"categorical_test": test, "p_value": float(p_value), "welch_t_p_value": float(welch_p)}
    except (ImportError, ValueError, ZeroDivisionError):
        return {"categorical_test": "unavailable", "p_value": None, "welch_t_p_value": None}


class ABTestRunner:
    def __init__(self, config: ABTestConfig, *, client_factory: Callable[[LLMConfig], Any] = LLMClient, sandbox_factory: Callable[[SandboxConfig], Any] = SandboxExecutor):
        self.config = config
        self.client_factory = client_factory
        self.sandbox_factory = sandbox_factory

    def run(self) -> Path:
        problems = ProblemLoader().load(self.config.dataset_path)
        if self.config.problem_filters:
            problems = ProblemLoader().filter_problems(problems, **self.config.problem_filters)
        if not problems:
            raise ValueError("A/B test requires at least one problem")
        assignment = stratified_assign(problems, self.config.prompt_variants, self.config.seed)
        output = self._create_output_dir()
        assignments = {
            problem.problem_id: {
                "variant": assignment[problem.problem_id],
                "difficulty": problem.difficulty,
                "tags": list(problem.tags),
            }
            for problem in problems
        }
        rows = []
        for variant in self.config.prompt_variants:
            rows.extend(self._run_variant(variant, [p for p in problems if assignment[p.problem_id] == variant.id]))
        report = self._build_report(rows, assignments, output)
        (output / "ab_test.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._write_csv(output / "results.csv", rows)
        (output / "REPORT.md").write_text(self._markdown(report), encoding="utf-8")
        return output

    def _run_variant(self, variant, problems):
        def run(problem):
            sandbox = self.sandbox_factory(self.config.sandbox_config)
            ok, detail = sandbox.health_check()
            if not ok:
                raise RuntimeError(f"Sandbox preflight failed: {detail}")
            client = PromptVariantClient(self.client_factory(self.config.model), variant)
            strategy = AlgorithmHarness.STRATEGY_MAP[self.config.strategy.name](self.config.strategy, client, sandbox)
            harness = AlgorithmHarness(HarnessConfig(llm_config=self.config.model, sandbox_config=self.config.sandbox_config, dataset_path=self.config.dataset_path, strategies=[self.config.strategy]))
            started = time.perf_counter()
            result = harness._execute_problem(self.config.strategy, problem, strategy, sandbox)
            return {
                "variant": variant.id, "problem_id": problem.problem_id, "difficulty": problem.difficulty, "tags": list(problem.tags),
                "status": result.status, "success": result.status == "success", "formal_evaluable": result.formal_evaluable,
                "formal_passed": bool(result.hidden_result and result.hidden_result.all_passed), "sample_passed": bool(result.final_result and result.final_result.all_passed),
                "failure_category": result.failure_category, "total_tokens": result.total_tokens,
                "elapsed_seconds": time.perf_counter() - started, "iterations": len(result.iterations), "error_message": result.error_message,
            }
        if self.config.max_workers == 1 or len(problems) < 2:
            return [run(problem) for problem in problems]
        with ThreadPoolExecutor(max_workers=min(self.config.max_workers, len(problems))) as pool:
            return list(pool.map(run, problems))

    def _build_report(self, rows, assignments, output):
        baseline = self.config.baseline.id
        treatment = self.config.treatment.id
        by_variant = {
            variant.id: [row for row in rows if row["variant"] == variant.id]
            for variant in self.config.prompt_variants
        }
        binary = {
            key: [int(row["success"]) for row in value]
            for key, value in by_variant.items()
        }
        formal = {
            key: [int(row["formal_passed"]) for row in value if row["formal_evaluable"]]
            for key, value in by_variant.items()
        }
        sample_diff = _proportion_ci(
            sum(binary[baseline]), len(binary[baseline]),
            sum(binary[treatment]), len(binary[treatment])
        )
        formal_diff = _proportion_ci(
            sum(formal[baseline]), len(formal[baseline]),
            sum(formal[treatment]), len(formal[treatment])
        )
        stats = _statistical_tests(binary[baseline], binary[treatment])
        grouped = self._grouped_rates(rows)
        return redact_sensitive_data({
            "schema_version": "1.0",
            "name": self.config.name or "ab-test",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "output_dir": str(output),
            "seed": self.config.seed,
            "model": self.config.model.redacted_dict(),
            "strategy": self.config.strategy.model_dump(mode="json"),
            "variants": [variant.model_dump(mode="json") for variant in self.config.prompt_variants],
            "baseline_id": baseline,
            "treatment_id": treatment,
            "assignments": assignments,
            "balance": self._balance(assignments),
            "comparison": {
                "sample": {
                    "baseline": self._rate(binary[baseline]),
                    "treatment": self._rate(binary[treatment]),
                    "ci95": sample_diff,
                },
                "formal": {
                    "baseline": self._rate(formal[baseline]),
                    "treatment": self._rate(formal[treatment]),
                    "ci95": formal_diff,
                },
                "statistics": stats,
                "elapsed_seconds": {
                    key: sum(row["elapsed_seconds"] for row in value)
                    for key, value in by_variant.items()
                },
                "tokens": {
                    key: sum(row["total_tokens"] for row in value)
                    for key, value in by_variant.items()
                },
                "failure_categories": {
                    key: self._failure_counts(value)
                    for key, value in by_variant.items()
                },
            },
            "by_difficulty": grouped["difficulty"],
            "by_tag": grouped["tag"],
            "recommendation": self._recommendation(stats, sample_diff),
            "rows": rows,
        })

    @staticmethod
    def _rate(values):
        return sum(values) / len(values) if values else None

    @staticmethod
    def _failure_counts(rows):
        counts = defaultdict(int)
        for row in rows:
            if row["failure_category"]:
                counts[row["failure_category"]] += 1
        return dict(counts)

    @staticmethod
    def _balance(assignments):
        strata = defaultdict(lambda: defaultdict(int))
        for item in assignments.values():
            strata[str((item["difficulty"], tuple(sorted(item["tags"]))))][item["variant"]] += 1
        return {key: dict(value) for key, value in strata.items()}

    @staticmethod
    def _grouped_rates(rows):
        grouped = {"difficulty": defaultdict(lambda: [0, 0]), "tag": defaultdict(lambda: [0, 0])}
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
    def _recommendation(stats, sample_ci):
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
    def _write_csv(path, rows):
        fields = [
            "variant", "problem_id", "difficulty", "status", "success",
            "formal_evaluable", "formal_passed", "sample_passed", "failure_category",
            "total_tokens", "elapsed_seconds", "iterations",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({field: row.get(field) for field in fields} for row in rows)

    @staticmethod
    def _markdown(report):
        comparison = report["comparison"]
        lines = [
            f"# A/B Test: {report['name']}",
            "",
            f"Baseline: `{report['baseline_id']}`",
            f"Treatment: `{report['treatment_id']}`",
            f"Seed: `{report['seed']}`",
            "",
            "| Variant | Sample rate | Formal rate | Tokens | Seconds |",
            "|---|---:|---:|---:|---:|",
        ]
        for variant in report["variants"]:
            variant_id = variant["id"]
            lines.append(
                f"| {variant_id} | {comparison['sample'][variant_id]} | "
                f"{comparison['formal'][variant_id]} | {comparison['tokens'][variant_id]} | "
                f"{comparison['elapsed_seconds'][variant_id]:.3f} |"
            )
        lines.extend([
            "", f"p-value: {comparison['statistics'].get('p_value')}",
            "", report["recommendation"], "",
        ])
        return "\n".join(lines)

    def _create_output_dir(self):
        base = Path(self.config.output_dir)
        name = f"ab-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        output = base / name
        suffix = 1
        while output.exists():
            suffix += 1
            output = base / f"{name}-{suffix}"
        output.mkdir(parents=True)
        return output
