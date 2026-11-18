"""
Fixed-budget experiment runner (issue #15).

Executes model x strategy x repeat combinations over one dataset under
identical per-problem budget caps, persists every combination with the same
on-disk shape as regular runs, and records the metadata needed to audit and
rebuild the experiment: dataset fingerprint, code version, effective model
parameters, budget definition, and a pricing snapshot.
"""

import hashlib
import json
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.budget import BudgetTracker
from src.checkpoints import UnitCheckpoint, write_checkpoint
from src.experiment_panel import generate_html_panel
from src.experiment_report import generate_comparison_report
from src.harness import AlgorithmHarness
from src.llm_client import SpendObserver
from src.models import ExperimentConfig, HarnessConfig, LLMConfig, Problem, StrategyConfig
from src.problem_loader import ProblemLoader
from src.task_service import TaskService
from src.utils.logging import get_logger
from src.utils.pricing import PricingManager
from src.utils.secrets import redact_sensitive_data

logger = get_logger(__name__)
EXPERIMENT_SCHEMA_VERSION = "1.1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> str | None:
    """Resolve the current git commit, or None outside a repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            encoding="utf-8",
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            encoding="utf-8",
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


class ExperimentRunner:
    """Run one experiment configuration end to end."""

    def __init__(self, config: ExperimentConfig, pricing_file: str | None = None):
        self.config = config
        self.pricing_manager = PricingManager(pricing_file)
        self.should_pause: Callable[[], bool] | None = None
        self.on_combination: Callable[[int, int, str, str, int], None] | None = None
        self.paused = False
        self.checkpoint_dir: Path | None = None
        self.on_spend: SpendObserver | None = None
        self.before_generate: Callable[[], None] | None = None

    def _report_combination(
        self,
        completed: int,
        total: int,
        model: LLMConfig,
        strategy: StrategyConfig,
        repeat: int,
    ) -> None:
        if self.on_combination is None:
            return
        self.on_combination(completed, total, model.model, strategy.name, repeat)

    def _pause_requested(self) -> bool:
        if self.should_pause is None or not self.should_pause():
            return False
        self.paused = True
        return True

    def run(self) -> Path:
        """Execute all combinations and return the experiment directory."""
        ExperimentConfig.model_validate(self.config.model_dump())
        started_at = datetime.now().isoformat()
        problems = self._load_problems()
        exp_dir = self._create_experiment_dir()
        metadata_path = exp_dir / "experiment.json"
        dataset = self._dataset_fingerprint(problems)

        metadata: dict[str, Any]
        if self.checkpoint_dir is not None and metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
                raise ValueError(
                    "Unsupported experiment checkpoint format "
                    f"{metadata.get('schema_version')!r}; start a new experiment"
                )
        else:
            metadata = {
                "schema_version": EXPERIMENT_SCHEMA_VERSION,
                "name": self.config.name,
                "experiment_id": exp_dir.name,
                "sampling_run_id": uuid4().hex,
                "created_at": started_at,
                "code_version": {"git_commit": _git_commit(), "git_dirty": _git_dirty()},
                "dataset": dataset,
                "budget": self.config.budget.model_dump() if self.config.budget else None,
                "sandbox_config": self.config.sandbox_config.model_dump(mode="json"),
                "problem_filters": self.config.problem_filters,
                "repeats": self.config.repeats,
                "models": [model.redacted_dict() for model in self.config.models],
                "strategies": [strategy.model_dump() for strategy in self.config.strategies],
                "pricing_snapshot": {
                    model.model: self.pricing_manager.get_pricing(model.model).to_dict()
                    for model in self.config.models
                },
                "combinations": [],
            }

        checkpoint = None
        if self.checkpoint_dir is not None:
            checkpoint_config = self.config.redacted_dict()
            checkpoint_config.pop("dataset_path", None)
            checkpoint_dataset = dataset.copy()
            checkpoint_dataset.pop("path", None)
            checkpoint = UnitCheckpoint(
                exp_dir / "units",
                TaskService.config_fingerprint(
                    {"config": checkpoint_config, "dataset": checkpoint_dataset}
                ),
            )

        recorded_sampling_policy = "sampling_run_id" in metadata
        if not recorded_sampling_policy:
            metadata["sampling_run_id"] = uuid4().hex

        combinations = (
            (model, strategy, repeat)
            for model in self.config.models
            for strategy in self.config.strategies
            for repeat in range(1, self.config.repeats + 1)
        )
        all_jobs = {f"combo-{index}": combo for index, combo in enumerate(combinations)}
        completed = {combo["combo_id"]: combo for combo in metadata["combinations"]}
        if len(completed) != len(metadata["combinations"]) or completed.keys() - all_jobs.keys():
            raise ValueError("Invalid combination IDs in experiment checkpoint metadata")
        total = len(all_jobs)
        remaining = []
        for combo_id, (model, strategy, repeat) in all_jobs.items():
            saved = completed.get(combo_id)
            if saved is None and checkpoint is not None:
                saved = checkpoint.get(combo_id)
            if saved is None:
                remaining.append((combo_id, model, strategy, repeat))
                continue
            if (
                saved.get("combo_id"),
                saved.get("combo_dir"),
                saved.get("model"),
                saved.get("strategy"),
                saved.get("repeat"),
            ) != (combo_id, combo_id, model.model, strategy.name, repeat):
                raise ValueError(f"Mismatched experiment checkpoint for combination {combo_id!r}")
            if (
                not recorded_sampling_policy
                and model.cache.enabled
                and self._requires_independent_sampling(strategy)
                and not saved.get("sampling_scope")
            ):
                raise ValueError(
                    "This experiment checkpoint predates independent sampling; start a new experiment"
                )
            if combo_id not in completed:
                metadata["combinations"].append(saved)
            logger.info(
                "experiment_combination_recovered",
                experiment_id=exp_dir.name,
                sampling_run_id=metadata.get("sampling_run_id"),
                combo_id=combo_id,
                sampling_scope=saved.get("sampling_scope"),
            )
        self._write_json(metadata_path, metadata)

        def run_combo(
            combo_id: str, model: LLMConfig, strategy: StrategyConfig, repeat: int
        ) -> dict[str, Any] | None:
            if self._pause_requested():
                return None
            combo = self._run_combo(exp_dir / combo_id, model, strategy, repeat)
            if checkpoint is not None:
                checkpoint.put(combo_id, combo)
            return combo

        jobs = remaining
        if self.config.execution == "parallel" and len(jobs) > 1:
            workers = min(self.config.max_workers, len(jobs))
            logger.info("experiment_parallel_start", jobs=len(jobs), workers=workers)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # Iterate futures in submission order so the recorded
                # combination order stays identical to serial execution.
                # Combinations already submitted may finish; later ones do not start.
                futures = []
                for combo_id, model, strategy, repeat in jobs:
                    if self._pause_requested():
                        break
                    self._report_combination(
                        len(metadata["combinations"]), total, model, strategy, repeat
                    )
                    futures.append(pool.submit(run_combo, combo_id, model, strategy, repeat))
                for future in futures:
                    combo = future.result()
                    if combo is not None:
                        metadata["combinations"].append(combo)
                    self._write_json(exp_dir / "experiment.json", metadata)
        else:
            for combo_id, model, strategy, repeat in jobs:
                if self._pause_requested():
                    break
                self._report_combination(
                    len(metadata["combinations"]), total, model, strategy, repeat
                )
                combo = run_combo(combo_id, model, strategy, repeat)
                if combo is not None:
                    metadata["combinations"].append(combo)
                self._write_json(exp_dir / "experiment.json", metadata)

        if self.paused:
            self._write_json(exp_dir / "experiment.json", metadata)
            logger.info(
                "experiment_paused",
                experiment_id=exp_dir.name,
                combinations=len(metadata["combinations"]),
            )
            return exp_dir

        metadata["finished_at"] = datetime.now().isoformat()
        self._write_json(exp_dir / "experiment.json", metadata)
        logger.info(
            "experiment_completed",
            experiment_id=exp_dir.name,
            combinations=len(metadata["combinations"]),
        )
        generate_comparison_report(exp_dir)
        generate_html_panel(exp_dir)
        return exp_dir

    def _load_problems(self) -> list[Problem]:
        """Load the dataset with configured filters for fingerprinting."""
        problems = ProblemLoader().load(self.config.dataset_path)
        if self.config.problem_filters:
            problems = ProblemLoader().filter_problems(problems, **self.config.problem_filters)
        if not problems:
            raise ValueError("No problems available for the experiment")
        return problems

    def _dataset_fingerprint(self, problems: list[Problem]) -> dict[str, Any]:
        dataset_path = Path(self.config.dataset_path)
        return {
            "path": str(dataset_path),
            "sha256": _sha256_file(dataset_path) if dataset_path.exists() else None,
            "problem_count": len(problems),
            "problem_ids": [problem.problem_id for problem in problems],
            "problems": [
                {
                    "problem_id": problem.problem_id,
                    "difficulty": problem.difficulty,
                    "tags": list(problem.tags),
                }
                for problem in problems
            ],
        }

    def _create_experiment_dir(self) -> Path:
        if self.checkpoint_dir is not None:
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            return self.checkpoint_dir
        base = Path(self.config.output_dir)
        timestamp = datetime.now().strftime("exp-%Y%m%d-%H%M%S")
        exp_dir = base / timestamp
        suffix = 1
        while exp_dir.exists():
            suffix += 1
            exp_dir = base / f"{timestamp}-{suffix}"
        exp_dir.mkdir(parents=True)
        return exp_dir

    def _requires_independent_sampling(self, strategy: StrategyConfig) -> bool:
        return self.config.repeats > 1 or strategy.name == "self_consistency"

    def _run_combo(
        self,
        combo_dir: Path,
        model: LLMConfig,
        strategy: StrategyConfig,
        repeat: int,
    ) -> dict[str, Any]:
        combo_id = combo_dir.name
        combo_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "experiment_combo_started",
            combo=combo_id,
            model=model.model,
            strategy=strategy.name,
            repeat=repeat,
        )

        harness_config = HarnessConfig(
            llm_config=model,
            dataset_path=self.config.dataset_path,
            strategies=[strategy],
            sandbox_config=self.config.sandbox_config,
            output_dir=str(combo_dir),
            problem_filters=self.config.problem_filters,
        )
        tracker = BudgetTracker(self.config.budget)
        harness = AlgorithmHarness(harness_config, budget_tracker=tracker)
        sampling_scope = uuid4().hex if self._requires_independent_sampling(strategy) else None
        harness.sampling_scope = sampling_scope
        harness.pricing_manager = self.pricing_manager
        harness.before_generate = self.before_generate
        if self.on_spend is not None:
            on_spend = self.on_spend

            def record(event_id: str, response: Any, cached: bool) -> None:
                problem_id = tracker.current_problem
                problem = harness.problems_by_id.get(problem_id or "")
                on_spend(
                    event_id,
                    response,
                    cached,
                    {
                        "model": model.model,
                        "strategy": strategy.name,
                        "problem_id": problem_id,
                        "difficulty": problem.difficulty if problem is not None else None,
                    },
                )

            harness.on_response = record
        reports = harness.run()

        summary = redact_sensitive_data(
            {name: report.model_dump() for name, report in reports.items()}
        )
        self._write_json(combo_dir / "summary.json", summary)
        for strategy_name, results in harness.results.items():
            self._write_json(
                combo_dir / f"{strategy_name}_results.json",
                redact_sensitive_data([r.model_dump() for r in results]),
            )
        ledger = {
            "budget": self.config.budget.model_dump() if self.config.budget else None,
            "token_budget_unsupported": tracker.token_budget_unsupported,
            "problems": list(tracker.ledger.values()),
        }
        self._write_json(combo_dir / "budget_ledger.json", ledger)

        return {
            "combo_id": combo_id,
            "model": model.model,
            "strategy": strategy.name,
            "repeat": repeat,
            "sampling_scope": sampling_scope,
            "combo_dir": combo_id,
            "token_budget_unsupported": tracker.token_budget_unsupported,
        }

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        write_checkpoint(path, payload)
