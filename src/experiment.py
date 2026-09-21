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
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.budget import BudgetTracker
from src.harness import AlgorithmHarness
from src.models import ExperimentConfig, HarnessConfig, StrategyConfig
from src.problem_loader import ProblemLoader
from src.utils.logging import get_logger
from src.utils.pricing import PricingManager
from src.utils.secrets import redact_sensitive_data

logger = get_logger(__name__)


def _safe_dirname(value: str) -> str:
    """Make a model/strategy name safe to use as a directory name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unnamed"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit() -> Optional[str]:
    """Resolve the current git commit, or None outside a repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
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
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


class ExperimentRunner:
    """Run one experiment configuration end to end."""

    def __init__(self, config: ExperimentConfig, pricing_file: Optional[str] = None):
        self.config = config
        self.pricing_manager = PricingManager(pricing_file)

    def run(self) -> Path:
        """Execute all combinations and return the experiment directory."""
        started_at = datetime.now().isoformat()
        problems = self._load_problems()
        exp_dir = self._create_experiment_dir()

        metadata: Dict[str, Any] = {
            "schema_version": "1.0",
            "name": self.config.name,
            "experiment_id": exp_dir.name,
            "created_at": started_at,
            "code_version": {"git_commit": _git_commit(), "git_dirty": _git_dirty()},
            "dataset": self._dataset_fingerprint(problems),
            "budget": self.config.budget.model_dump() if self.config.budget else None,
            "repeats": self.config.repeats,
            "models": [model.redacted_dict() for model in self.config.models],
            "strategies": [strategy.model_dump() for strategy in self.config.strategies],
            "pricing_snapshot": {
                model.model: self.pricing_manager.get_pricing(model.model).to_dict()
                for model in self.config.models
            },
            "combinations": [],
        }
        self._write_json(exp_dir / "experiment.json", metadata)

        for model in self.config.models:
            for strategy in self.config.strategies:
                for repeat in range(1, self.config.repeats + 1):
                    combo = self._run_combo(exp_dir, model, strategy, repeat)
                    metadata["combinations"].append(combo)
                    self._write_json(exp_dir / "experiment.json", metadata)

        metadata["finished_at"] = datetime.now().isoformat()
        self._write_json(exp_dir / "experiment.json", metadata)
        logger.info(
            "experiment_completed",
            experiment_id=exp_dir.name,
            combinations=len(metadata["combinations"]),
        )
        return exp_dir

    def _load_problems(self):
        """Load the dataset with configured filters for fingerprinting."""
        problems = ProblemLoader().load(self.config.dataset_path)
        if self.config.problem_filters:
            problems = ProblemLoader().filter_problems(problems, **self.config.problem_filters)
        if not problems:
            raise ValueError("No problems available for the experiment")
        return problems

    def _dataset_fingerprint(self, problems) -> Dict[str, Any]:
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
        base = Path(self.config.output_dir)
        timestamp = datetime.now().strftime("exp-%Y%m%d-%H%M%S")
        exp_dir = base / timestamp
        suffix = 1
        while exp_dir.exists():
            suffix += 1
            exp_dir = base / f"{timestamp}-{suffix}"
        exp_dir.mkdir(parents=True)
        return exp_dir

    def _run_combo(
        self,
        exp_dir: Path,
        model,
        strategy: StrategyConfig,
        repeat: int,
    ) -> Dict[str, Any]:
        combo_id = f"{_safe_dirname(model.model)}__{_safe_dirname(strategy.name)}__r{repeat}"
        combo_dir = exp_dir / combo_id
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
            "combo_dir": combo_id,
            "token_budget_unsupported": tracker.token_budget_unsupported,
        }

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
