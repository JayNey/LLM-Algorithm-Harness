"""
Main entry point for LLM Algorithm Harness.
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

from src.failure_report import (
    render_failure_mode_chart,
    render_failure_mode_markdown,
    summarize_failure_modes,
)
from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
from src.models import CostAlertConfig, HarnessConfig, LLMConfig, SandboxConfig, StrategyConfig
from src.utils.config import load_config
from src.utils.logging import get_logger, setup_logging
from src.utils.secrets import redact_sensitive_data

logger = get_logger(__name__)

SUPPORTED_STRATEGIES = tuple(AlgorithmHarness.STRATEGY_MAP)


def positive_int(value: str) -> int:
    """Parse a strictly positive integer for argparse."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    """Parse a strictly positive finite float for argparse."""
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a number")
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_cost_alert_thresholds(value: str) -> list[int]:
    """Parse a comma-separated list of integer budget percentages."""
    try:
        values = [int(item.strip()) for item in value.split(",")]
        return CostAlertConfig(thresholds=values).thresholds
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(
            "thresholds must be unique integer percentages between 1 and 99"
        ) from exc


def confidence_threshold(value: str) -> float:
    """Parse a confidence threshold in the inclusive [0, 1] range."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number between 0 and 1") from exc
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return parsed


def apply_cli_overrides(config: HarnessConfig, args: argparse.Namespace) -> HarnessConfig:
    """Apply only values that the user explicitly supplied on the command line."""
    if args.dataset is not None:
        config.dataset_path = args.dataset
    if args.output is not None:
        config.output_dir = args.output

    configured_names = [strategy.name for strategy in config.strategies]
    unknown_names = sorted(set(configured_names) - set(SUPPORTED_STRATEGIES))
    if unknown_names:
        raise ValueError(f"Unknown configured strategies: {', '.join(unknown_names)}")

    if args.strategy is not None:
        config.strategies = [
            strategy for strategy in config.strategies if strategy.name == args.strategy
        ]

    if not config.strategies:
        if args.strategy:
            raise ValueError(f"Strategy '{args.strategy}' is not enabled in the configuration")
        raise ValueError("At least one valid strategy must be configured")

    filters = dict(config.problem_filters or {})
    for key in ("difficulty", "tags", "limit"):
        value = getattr(args, key)
        if value is not None:
            filters[key] = value

    limit = filters.get("limit")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
        raise ValueError("Problem limit must be a positive integer")
    config.problem_filters = filters or None

    if args.difficulty_strategy:
        mapping = {}
        for item in args.difficulty_strategy:
            difficulty, sep, strategy_name = item.partition("=")
            difficulty = difficulty.strip().lower()
            strategy_name = strategy_name.strip()
            if not sep or not difficulty or not strategy_name:
                raise ValueError(f"--difficulty-strategy expects DIFF=STRATEGY pairs, got '{item}'")
            if difficulty in mapping:
                raise ValueError(f"Duplicate difficulty in --difficulty-strategy: '{difficulty}'")
            mapping[difficulty] = strategy_name
        config.difficulty_strategy = mapping
    if args.budget_cap is not None:
        config.budget_cap_usd = args.budget_cap

    if getattr(args, "auto_stop_on_budget", False):
        config.budget_action = "auto_stop"
    elif getattr(args, "downgrade_on_budget", False):
        config.budget_action = "downgrade"

    thresholds = getattr(args, "cost_alert_thresholds", None)
    if thresholds is not None:
        existing = config.cost_alerts.model_dump() if config.cost_alerts else {}
        config.cost_alerts = CostAlertConfig(**{**existing, "thresholds": thresholds})

    if config.budget_cap_usd is None:
        if config.budget_action is not None or config.cost_alerts is not None:
            raise ValueError("Cost alerts and budget action require budget_cap_usd (--budget-cap)")
    elif config.budget_action == "downgrade" and not config.difficulty_strategy:
        raise ValueError("--downgrade-on-budget requires a difficulty_strategy mapping")
    elif config.budget_action is None and not config.difficulty_strategy:
        raise ValueError("budget_cap_usd (--budget-cap) requires a difficulty_strategy mapping or --auto-stop-on-budget")
    if config.difficulty_strategy:
        if args.strategy is not None:
            raise ValueError("--strategy cannot be combined with --difficulty-strategy")
        unknown = sorted(set(config.difficulty_strategy.values()) - set(SUPPORTED_STRATEGIES))
        if unknown:
            raise ValueError(
                "Unknown strategy in difficulty-strategy mapping: " f"{', '.join(unknown)}"
            )

    return config


def config_file_overrides(args: argparse.Namespace) -> dict:
    """Build explicit CLI values that must apply before config validation."""
    overrides = {}
    if args.dataset is not None:
        overrides["dataset_path"] = args.dataset
    if args.output is not None:
        overrides["output_dir"] = args.output

    filters = {
        key: getattr(args, key)
        for key in ("difficulty", "tags", "limit")
        if getattr(args, key) is not None
    }
    if filters:
        overrides["problem_filters"] = filters
    return overrides


def create_default_config(dataset_path: str, output_dir: str) -> HarnessConfig:
    """
    Create default configuration.

    Args:
        dataset_path: Path to dataset
        output_dir: Output directory

    Returns:
        HarnessConfig
    """
    return HarnessConfig(
        dataset_path=dataset_path,
        output_dir=output_dir,
        llm_config=LLMConfig(
            provider="openai",
            api_key="",  # Will use environment variable
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=2000,
            timeout=30,
        ),
        sandbox_config=SandboxConfig(
            timeout_seconds=5,
            memory_limit_mb=256,
            allowed_imports=["math", "itertools", "collections", "functools", "heapq", "bisect"],
        ),
        strategies=[
            StrategyConfig(name="vanilla", max_iterations=1),
            StrategyConfig(name="chain_of_thought", max_iterations=1),
            StrategyConfig(name="multi_round_feedback", max_iterations=3),
        ],
    )


def print_report(reports: dict):
    """
    Print evaluation reports.

    Args:
        reports: Dict of strategy reports
    """
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80 + "\n")

    for strategy_name, report in reports.items():
        print(f"Strategy: {strategy_name}")
        print(f"  Success Rate: {report.success_rate:.2%}")
        print(f"  Solved: {report.solved_problems}/{report.total_problems}")
        print(
            "  Formal Hidden Evaluation: "
            f"{report.formal_solved_problems}/{report.formal_evaluable_problems} "
            f"({report.formal_success_rate:.2%})"
        )
        print(f"  Sample-only Problems: {report.sample_only_problems}")
        print(f"  Avg Attempts: {report.avg_attempts_per_problem:.2f}")
        print(f"  Avg Tokens: {report.avg_tokens_per_problem:.0f}")
        cost_pricing = report.pricing_metadata or {}
        if cost_pricing.get("unknown_usage") or cost_pricing.get("unknown_pricing"):
            print("  Estimated Cost: 未知")
        else:
            print(f"  Estimated Cost: ${report.estimated_cost_usd:.4f}")
        print()


def create_run_dir(output_dir: str, run_id: str | None = None) -> Path:
    """
    Create a timestamped directory for this run's results.

    Args:
        output_dir: Base output directory

    Returns:
        Path to the created run directory
    """
    run_id = run_id or datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_path = Path(output_dir) / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def save_results(reports: dict, output_dir: str, harness: AlgorithmHarness, config: HarnessConfig):
    """
    Save results to a timestamped run directory.

    Layout:
        <output_dir>/
        ├── latest.json                     # pointer to the most recent run
        └── run-YYYYMMDD-HHMMSS/
            ├── metadata.json               # model, dataset, redacted config snapshot
            ├── summary.json
            └── <strategy>_results.json

    Args:
        reports: Strategy reports
        output_dir: Base output directory
        harness: Harness instance with results
        config: Harness config used for this run (api_key is redacted)
    """
    task_run_id = getattr(getattr(harness, "task_record", None), "run_id", None)
    if not isinstance(task_run_id, str):
        task_run_id = None
    run_path = create_run_dir(output_dir, task_run_id)

    # Save run metadata: what model/dataset/config produced these results
    config_dict = config.redacted_dump()
    llm_config = config_dict.get("llm_config", {})

    first_strategy = next(iter(harness.results.values()), [])
    metadata = {
        "run_id": run_path.name,
        "timestamp": datetime.now().isoformat(),
        "dataset_path": config.dataset_path,
        "num_problems": len(first_strategy),
        "strategies": list(harness.results.keys()),
        "llm": {
            "provider": llm_config.get("provider"),
            "model": llm_config.get("model"),
            "base_url": llm_config.get("base_url"),
        },
        "config": config_dict,
    }
    task_record = getattr(harness, "task_record", None)
    if isinstance(task_run_id, str) and task_record is not None:
        metadata["task"] = {
            "state": task_record.state,
            "total_units": task_record.total_units,
            "completed_units": task_record.completed_units,
            "config_fingerprint": task_record.config_fingerprint,
            "dataset_fingerprint": task_record.dataset_fingerprint,
        }
    metadata_file = run_path / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("metadata_saved", path=str(metadata_file))

    # Save summary report
    summary = redact_sensitive_data(
        {"strategies": {name: report.model_dump() for name, report in reports.items()}}
    )

    problem_objects = getattr(harness, "problems_by_id", {})
    problem_info = (
        {key: problem.model_dump(mode="json") for key, problem in problem_objects.items()}
        if isinstance(problem_objects, dict) else {}
    )
    by_strategy_results = {
        name: [result.model_dump(mode="json") for result in results]
        for name, results in harness.results.items()
    }
    failure_modes = {
        "overall": summarize_failure_modes(
            [row for rows in by_strategy_results.values() for row in rows], problem_info
        ),
        "by_strategy": {
            name: summarize_failure_modes(rows, problem_info)
            for name, rows in by_strategy_results.items()
        },
    }
    summary["failure_modes"] = redact_sensitive_data(failure_modes)

    cost_monitor = getattr(harness, "cost_monitor", None)
    if cost_monitor is not None and (
        config.budget_cap_usd is not None or config.difficulty_strategy
    ):
        summary["cost_control"] = {
            **cost_monitor.snapshot(),
            "budget_action": config.budget_action or (
                "downgrade" if config.difficulty_strategy and config.budget_cap_usd else None
            ),
            "incomplete": task_record is not None and task_record.state == "paused",
        }

    summary_file = run_path / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("summary_saved", path=str(summary_file))

    (run_path / "failure_mode_summary.json").write_text(
        json.dumps(summary["failure_modes"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failure_markdown = [render_failure_mode_markdown(failure_modes["overall"])]
    chart = render_failure_mode_chart(failure_modes["overall"])
    if chart is not None:
        (run_path / "failure_mode_distribution.png").write_bytes(chart)
        failure_markdown.append("\n![失败模式分布](failure_mode_distribution.png)\n")
    for name, strategy_summary in failure_modes["by_strategy"].items():
        failure_markdown.append(f"\n## 策略：{name}\n")
        failure_markdown.append(
            render_failure_mode_markdown(strategy_summary).replace(
                "## 失败模式分析", "### 失败模式分析", 1
            ).replace("### 按题目标签", "#### 按题目标签").replace(
                "### 高频弱项", "#### 高频弱项"
            )
        )
    (run_path / "failure_mode_report.md").write_text(
        "\n".join(failure_markdown), encoding="utf-8"
    )

    if task_record is not None and task_record.state == "paused":
        cutoff = {
            "run_id": task_run_id,
            "timestamp": datetime.now().isoformat(),
            "state": "paused",
            "reason": "known_cost_reached_budget_cap",
            **cost_monitor.snapshot(),
            "completed_units": task_record.completed_units,
            "queued_units": sum(unit.status == "queued" for unit in task_record.units),
            "total_units": task_record.total_units,
            "note": "Unknown-price or missing-usage calls are excluded from the known cost total.",
        }
        cutoff_file = run_path / "cost_cutoff.json"
        cutoff_file.write_text(json.dumps(cutoff, indent=2), encoding="utf-8")
        logger.warning("budget_run_paused", report=str(cutoff_file))

    # Save detailed results per strategy
    for strategy_name, results in harness.results.items():
        results_file = run_path / f"{strategy_name}_results.json"
        results_data = redact_sensitive_data([r.model_dump() for r in results])

        with open(results_file, "w") as f:
            json.dump(results_data, f, indent=2)

        logger.info("strategy_results_saved", strategy=strategy_name, path=str(results_file))

    # Update the latest-run pointer for tooling
    latest_file = Path(output_dir) / "latest.json"
    with open(latest_file, "w") as f:
        json.dump({"latest_run": run_path.name}, f, indent=2)

    print(f"\nResults saved to: {run_path}")


def run_import_command(args: argparse.Namespace) -> int:
    """
    Execute the import command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure, 3=strict mode failure)
    """
    from src.importers.base import ImportResult
    from src.importers.codeforces import CodeforcesImporter
    from src.importers.leetcode import LeetCodeImporter
    from src.importers.livecodebench import LiveCodeBenchImporter
    from src.importers.local_json import LocalJsonImporter
    from src.importers.mock import MockPlatformImporter
    from src.problem_loader import ProblemLoader

    # Map source type to importer class
    IMPORTERS = {
        "codeforces": CodeforcesImporter,
        "local-json": LocalJsonImporter,
        "leetcode": LeetCodeImporter,
        "livecodebench": LiveCodeBenchImporter,
        "mock": MockPlatformImporter,
    }

    source_name = args.source or args.import_source
    if source_name not in IMPORTERS:
        print(
            f"Error: --source is required. Supported types: {', '.join(IMPORTERS.keys())}",
            file=sys.stderr,
        )
        return 2

    try:
        # Instantiate importer
        importer_class = IMPORTERS[source_name]
        if source_name == "codeforces":
            tags = []
            for value in args.tags or []:
                tags.extend(item.strip() for item in value.split(",") if item.strip())
            importer = importer_class(
                contest=args.contest,
                min_rating=args.min_rating,
                max_rating=args.max_rating,
                tags=tags,
                limit=args.import_limit,
            )
        elif source_name == "livecodebench":
            importer = importer_class(
                release_version=args.release_version,
                start_date=args.start_date,
                end_date=args.end_date,
                difficulty=args.import_difficulty,
                limit=args.import_limit,
            )
        else:
            importer = importer_class()

        # Preview mode indicator
        if args.preview:
            print("[PREVIEW MODE]")
            print()

        # Fetch and transform problems
        source_input = args.input or "codeforces-api"
        if source_name != "codeforces" and not args.input:
            print("Error: --input is required for this source", file=sys.stderr)
            return 2
        logger.info("import_starting", source=source_name, input=source_input)
        raw_data = importer.fetch_problems(source_input)
        problems = importer.transform_to_schema(raw_data)

        # Validate problems
        valid_problems, failed_items = importer.validate_problems(problems)
        failed_items = list(getattr(importer, "transform_failures", [])) + failed_items

        # Load existing dataset
        existing_problems = []
        output_path = Path(args.output)
        if output_path.exists():
            loader = ProblemLoader()
            existing_problems = loader.load(str(output_path))
            logger.info("existing_dataset_loaded", count=len(existing_problems))

        # Detect duplicates
        final_problems, skipped_ids, overwritten_ids = importer.detect_duplicates(
            valid_problems, existing_problems, args.update_strategy
        )

        # Build import result
        result = ImportResult()
        result.successful = [p for p in valid_problems if p.problem_id not in skipped_ids]
        result.failed = failed_items
        result.duplicates_skipped = skipped_ids
        result.duplicates_overwritten = overwritten_ids
        result.warnings.extend(
            f"{problem.problem_id}: manual completion required"
            for problem in result.successful
            if problem.needs_manual_completion
        )

        # Display summary
        print(f"Import Summary:")
        print(f"  Total problems in input: {len(raw_data)}")
        print(f"  Successfully validated: {len(valid_problems)}")
        print(f"  Failed validation: {len(failed_items)}")
        print(f"  Duplicates (skipped): {len(skipped_ids)}")
        print(f"  Duplicates (overwritten): {len(overwritten_ids)}")
        print(
            "  Needs manual completion: "
            f"{sum(problem.needs_manual_completion for problem in result.successful)}"
        )
        print(
            f"  New problems to import: {len([p for p in valid_problems if p.problem_id not in skipped_ids and p.problem_id not in overwritten_ids])}"
        )
        print()

        # Show failed items
        if failed_items:
            print("Failed problems:")
            for item in failed_items[:5]:  # Show first 5
                print(f"  - Index {item['index']} (id: {item['problem_id']}): {item['error']}")
            if len(failed_items) > 5:
                print(f"  ... and {len(failed_items) - 5} more")
            print()

        # Confirmation (unless preview or force)
        if not args.preview and not args.force:
            response = input(f"Proceed with import? (y/N): ")
            if response.lower() != "y":
                print("Import cancelled.")
                return 0

        # Persist (unless preview mode)
        if not args.preview:
            importer.persist_dataset(final_problems, args.output)
            print(f"Dataset written to: {args.output}")
        else:
            print("No changes were made to the dataset (preview mode).")

        # Generate and display report
        report = importer.generate_report(result, source_input, args.output, args.preview)
        print()
        print("Import Report:")
        print(f"  Timestamp: {report['timestamp']}")
        print(f"  Successful: {report['summary']['successful']}")
        print(f"  Failed: {report['summary']['failed']}")
        print(f"  Duplicates skipped: {report['summary']['duplicates_skipped']}")
        print(f"  Duplicates overwritten: {report['summary']['duplicates_overwritten']}")

        # Determine exit code
        if result.all_failed:
            return 2
        elif result.has_failures:
            return 3 if args.strict else 1
        else:
            return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        logger.error("import_failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 2


def run_experiment_command(args: argparse.Namespace) -> int:
    """
    Execute a fixed-budget experiment (issue #15).

    Args:
        args: Parsed arguments with --config and optional --output-dir

    Returns:
        Exit code (0=success, 1=failure)
    """
    from src.experiment import ExperimentRunner
    from src.models import ExperimentConfig

    try:
        payload = json.loads(Path(args.config).read_text(encoding="utf-8"))
        payload.pop("comment", None)
        config = ExperimentConfig(**payload)

        unknown_names = sorted({s.name for s in config.strategies} - set(SUPPORTED_STRATEGIES))
        if unknown_names:
            raise ValueError(f"Unknown configured strategies: {', '.join(unknown_names)}")

        if args.output_dir is not None:
            config = config.model_copy(update={"output_dir": args.output_dir})

        logger.info(
            "experiment_starting",
            config=args.config,
            models=[m.model for m in config.models],
            strategies=[s.name for s in config.strategies],
            repeats=config.repeats,
        )
        exp_dir = ExperimentRunner(config).run()
        print("\nExperiment completed.")
        print(f"  Artifacts: {exp_dir}")
        print(f"  Comparison report: {exp_dir / 'REPORT.md'}")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        logger.error("experiment_failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_optimize_command(args: argparse.Namespace) -> int:
    """
    Produce a cost optimization advisory from a completed experiment (issue #56).

    Args:
        args: Parsed arguments with --experiment and optimization options

    Returns:
        Exit code (0=success, 1=failure)
    """
    from src.cost_optimizer import build_advisory, render_markdown

    exp_dir = Path(args.experiment)
    comparison_file = exp_dir / "comparison.json"
    if not comparison_file.exists():
        print(
            f"Error: comparison.json not found under {exp_dir}; "
            "run an experiment first (harness experiment --config ...).",
            file=sys.stderr,
        )
        return 1
    try:
        comparison = json.loads(comparison_file.read_text(encoding="utf-8"))
        advisory = build_advisory(
            comparison,
            budget=args.budget,
            min_accuracy=args.min_accuracy,
            objective=args.objective,
        )
        optimization_file = exp_dir / "optimization.json"
        with open(optimization_file, "w", encoding="utf-8") as f:
            json.dump(advisory, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(exp_dir / "OPTIMIZATION.md", "w", encoding="utf-8") as f:
            f.write(render_markdown(advisory))

        print("\nCost optimization advisory:")
        ranking = advisory["ranking"]["ranking"]
        if ranking:
            print(
                "  Best value: "
                + f"{ranking[0]['model']} × {ranking[0]['strategy']}"
                + f" (ratio {ranking[0]['ratio']})"
            )
        for name in ("highest_accuracy", "best_value", "lowest_cost"):
            rec = advisory["recommendations"][name]
            if rec.get("feasible"):
                print(
                    f"  {name}: {rec['model']} × {rec['strategy']}"
                    f" (accuracy {rec['accuracy']:.1%}, ${rec['cost_usd']:.4f})"
                )
            else:
                print(f"  {name}: {rec.get('note')}")
        if advisory.get("budget_plan"):
            plan = advisory["budget_plan"]
            print(
                f"  Budget plan: ${plan['estimated_cost']:.4f} of ${plan['budget']},"
                f" coverage {plan['coverage']} problems"
            )
        print(f"  Artifacts: {optimization_file} and {exp_dir / 'OPTIMIZATION.md'}")
        return 0
    except Exception as e:
        logger.error("optimize_failed", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_recommend_command(args: argparse.Namespace) -> int:
    """Analyze history and write a recommended problem dataset."""
    from src.recommender import RecommendationEngine

    try:
        report = RecommendationEngine(
            args.history,
            dataset_path=args.dataset,
            failure_threshold=args.failure_threshold,
            min_samples=args.min_samples,
        ).write(args.output, limit=args.limit)
        dataset_path = report["recommendation_config"]["dataset_path"]
        print(f"Recommendation report saved to: {args.output}")
        print(f"Recommended dataset saved to: {dataset_path}")
        print(f"Weak groups: {len(report['weakness_report'])}")
        print(f"Recommended problems: {len(report['recommended_problem_ids'])}")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_ab_test_command(args: argparse.Namespace) -> int:
    """Run a two-variant stratified prompt A/B test."""
    from src.ab_testing import ABTestConfig, ABTestRunner

    try:
        import yaml

        payload = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
        config = ABTestConfig.model_validate(payload)
        if args.output_dir:
            config = config.model_copy(update={"output_dir": args.output_dir})
        output = ABTestRunner(config).run()
        print(f"A/B test completed: {output}")
        print(f"  Report: {output / 'REPORT.md'}")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.error("ab_test_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_benchmark_command(args: argparse.Namespace) -> int:
    """Run benchmark evaluation for learning curve tracking."""
    from src.benchmark import BenchmarkManager
    from src.benchmark.executor import BenchmarkExecutor
    from src.utils.config import load_config

    try:
        manager = BenchmarkManager(".")

        # List available suites if requested
        if args.list_suites:
            suites = manager.list_suites()
            if not suites:
                print("No benchmark suites found.")
                return 0

            print("Available benchmark suites:")
            for suite_file in suites:
                print(f"  - {suite_file}")
            return 0

        # Load specified suite
        if not args.suite:
            print("Error: --suite is required", file=sys.stderr)
            print("Use --list-suites to see available benchmark suites", file=sys.stderr)
            return 1

        suite = manager.load_suite(args.suite)
        print(f"Loaded benchmark suite: {suite.name}")
        print(f"  Problems: {len(suite.problems)}")
        print(f"  Version: {suite.version}")
        print(f"  Frozen: {suite.frozen}")

        # Load harness config
        config = load_config()
        if not config:
            print("Error: No configuration found. Please provide a config file.", file=sys.stderr)
            return 1

        print(f"\nExecuting benchmark evaluation...")

        # Execute benchmark
        executor = BenchmarkExecutor(suite, config)
        results = executor.execute()

        print(f"\n✓ Benchmark evaluation completed!")
        print(f"  Suite: {results['suite']['name']}")
        print(f"  Problems evaluated: {results['problems_evaluated']}")
        if results['problems_missing'] > 0:
            print(f"  Problems missing: {results['problems_missing']}")

        print(f"\nResults by strategy:")
        for strategy_name, strategy_results in results['strategies'].items():
            print(f"  {strategy_name}:")
            print(f"    - Accuracy: {strategy_results['accuracy']:.2%}")
            print(f"    - Passed: {strategy_results['passed']}/{strategy_results['total']}")

        # TODO: Save results to history storage
        print("\nNote: History storage coming in next task...")

        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.error("benchmark_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_cache_command(args: argparse.Namespace) -> int:
    """Execute cache management commands."""
    from src.cache import LLMResponseCache

    try:
        cache = LLMResponseCache(
            cache_dir=".cache/llm_responses",
            enabled=True,
        )

        if args.cache_action == "clear":
            model_filter = args.model if hasattr(args, "model") and args.model else None
            cache.clear(model_filter=model_filter)
            if model_filter:
                print(f"Cache cleared for model: {model_filter}")
            else:
                print("All cache entries cleared.")
            return 0

        elif args.cache_action == "stats":
            stats = cache.stats()
            print("\nCache Statistics:")
            print(f"  Enabled: {stats['enabled']}")
            print(f"  Total entries: {stats['total_entries']}")
            print(f"  Disk usage: {stats['disk_usage_mb']:.2f} MB")
            print(f"  Hit rate: {stats['hit_rate']:.2%}")
            print(f"  Hits: {stats['hits']}")
            print(f"  Misses: {stats['misses']}")
            print(f"  API calls saved: {stats['api_calls_saved']}")
            return 0

        else:
            print(f"Error: Unknown cache action: {args.cache_action}", file=sys.stderr)
            return 1

    except Exception as exc:
        logger.error("cache_command_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_tags_normalize_command(args: argparse.Namespace) -> int:
    """Preview or write canonical tags for a problem dataset."""
    from src.utils.tag_manager import TagManager

    try:
        report = TagManager(args.mapping).normalize_dataset(
            args.dataset,
            output_path=args.output,
            apply_recommendations=args.apply_recommendations,
            min_confidence=args.min_confidence,
        )
        if args.report:
            report_path = Path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.output:
            print(f"Normalized dataset written to: {args.output}")
        else:
            print("Preview only: pass --output PATH after reviewing suggestions to write a dataset.")
        if args.report:
            print(f"Normalization report written to: {args.report}")
        return 0
    except (FileNotFoundError, TypeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM Algorithm Harness - Evaluate LLM problem-solving strategies"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Default command (run evaluation)
    run_parser = subparsers.add_parser("run", help="Run evaluation (default)")
    run_parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering: human-readable console (default) or machine-readable json",
    )
    run_parser.add_argument(
        "--dataset", type=str, help="Path to problem dataset JSON file (overrides config)"
    )
    run_parser.add_argument(
        "--config", type=str, help="Path to configuration JSON or YAML file (optional)"
    )
    run_parser.add_argument(
        "--output",
        "--output-dir",
        dest="output",
        type=str,
        help="Output directory for results (overrides config; default: ./results)",
    )
    run_parser.add_argument(
        "--strategy",
        type=str,
        choices=SUPPORTED_STRATEGIES,
        help="Run only specific strategy (optional, runs all by default)",
    )
    run_parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Filter problems by difficulty (overrides config)",
    )
    run_parser.add_argument(
        "--tags",
        nargs="+",
        help="Filter problems by one or more tags (overrides config)",
    )
    run_parser.add_argument(
        "--limit",
        type=positive_int,
        help="Limit number of problems to evaluate; must be positive (overrides config)",
    )
    run_parser.add_argument(
        "--run-id",
        help="Use a stable task run ID for persistence or resumption",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an existing task; requires --run-id and matching config/dataset fingerprints",
    )
    run_parser.add_argument(
        "--difficulty-strategy",
        nargs="+",
        metavar="DIFF=STRATEGY",
        help=(
            "Cost-sensitive selector: map each difficulty (easy/medium/hard) to a "
            "strategy, e.g. easy=vanilla medium=chain_of_thought hard=multi_round_feedback. "
            "Each problem runs once with its mapped strategy"
        ),
    )
    run_parser.add_argument(
        "--budget-cap",
        dest="budget_cap",
        type=positive_float,
        help=(
            "Run-level known cost cap in USD; use --auto-stop-on-budget to pause "
            "or --difficulty-strategy for the existing downgrade behavior"
        ),
    )
    budget_action = run_parser.add_mutually_exclusive_group()
    budget_action.add_argument(
        "--auto-stop-on-budget", action="store_true",
        help="Pause queued work once known cost reaches the budget cap and write a cutoff report",
    )
    budget_action.add_argument(
        "--downgrade-on-budget", action="store_true",
        help="Downgrade remaining problems to the cheapest mapped strategy at the cap",
    )
    run_parser.add_argument(
        "--cost-alert-thresholds", type=parse_cost_alert_thresholds,
        metavar="PCT,PCT,...",
        help="Alert at these budget percentages (default: 50,80,90)",
    )

    # Import command
    run_parser.add_argument(
        "--list-models",
        action="store_true",
        help=(
            "List provider model IDs via the free model listing endpoint and exit. "
            "Model size metadata is not reliably provided by the API and is shown as unknown. "
            "A generation-based connectivity check would incur billing."
        ),
    )

    run_parser.add_argument(
        "--check-connection",
        action="store_true",
        help=(
            "Verify provider credentials/connectivity via the free model listing endpoint "
            "and exit (no generation request, no billing). Generation-based checks would be billed."
        ),
    )

    import_parser = subparsers.add_parser("import", help="Import problems from external sources")
    import_parser.add_argument("import_source", nargs="?", help="Optional positional source, e.g. codeforces")
    import_parser.add_argument(
        "--source",
        type=str,
        help="Import source type (e.g., codeforces, local-json, leetcode, mock)",
    )
    import_parser.add_argument(
        "--input",
        type=str,
        required=False,
        help="Input path (file, directory, or URL)",
    )
    import_parser.add_argument(
        "--output",
        type=str,
        default="data/problems.json",
        help="Output dataset path (default: data/problems.json)",
    )
    import_parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: show what would be imported without writing",
    )
    import_parser.add_argument(
        "--update-strategy",
        choices=["skip", "overwrite"],
        default="skip",
        help="How to handle duplicate problems (default: skip)",
    )
    import_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    import_parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: return error exit code on any failure",
    )
    import_parser.add_argument(
        "--release-version",
        default="release_v6",
        help="LiveCodeBench release version (default: release_v6)",
    )
    import_parser.add_argument("--start-date", help="LiveCodeBench contest start date (YYYY-MM-DD)")
    import_parser.add_argument("--end-date", help="LiveCodeBench contest end date (YYYY-MM-DD)")
    import_parser.add_argument(
        "--import-difficulty",
        choices=["easy", "medium", "hard"],
        help="Filter LiveCodeBench imports by difficulty",
    )
    import_parser.add_argument(
        "--import-limit",
        type=positive_int,
        help="Limit LiveCodeBench imported problems",
    )
    import_parser.add_argument("--contest", help="Codeforces contest ID")
    import_parser.add_argument("--min-rating", type=int, help="Minimum Codeforces rating")
    import_parser.add_argument("--max-rating", type=int, help="Maximum Codeforces rating")
    import_parser.add_argument(
        "--tags", nargs="+", help="Codeforces tags; comma-separated or space-separated"
    )
    import_parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering",
    )

    experiment_parser = subparsers.add_parser(
        "experiment", help="Run fixed-budget model/strategy comparison experiments"
    )
    experiment_parser.add_argument(
        "--config",
        required=True,
        help="Path to the experiment configuration JSON (see experiment.example.json)",
    )
    experiment_parser.add_argument(
        "--output-dir",
        default=None,
        help="Override the configured experiment output directory",
    )
    experiment_parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering",
    )

    optimize_parser = subparsers.add_parser(
        "optimize", help="Cost optimization advisory from a completed experiment"
    )
    optimize_parser.add_argument(
        "--experiment",
        required=True,
        help="Path to the experiment directory containing comparison.json",
    )
    optimize_parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Budget in USD for the per-difficulty plan",
    )
    optimize_parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.0,
        help="Minimum accuracy constraint for recommendations (0-1)",
    )
    optimize_parser.add_argument(
        "--objective",
        choices=["highest_accuracy", "best_value", "lowest_cost"],
        default="best_value",
        help="Primary recommendation objective",
    )
    optimize_parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering",
    )

    recommend_parser = subparsers.add_parser(
        "recommend", help="Analyze evaluation history and recommend unevaluated problems"
    )
    recommend_parser.add_argument("--history", required=True, help="Results directory or JSON result file")
    recommend_parser.add_argument("--output", required=True, help="Recommendation report JSON path")
    recommend_parser.add_argument("--dataset", help="Problem dataset; inferred from history metadata when omitted")
    recommend_parser.add_argument(
        "--failure-threshold", type=float, default=0.5,
        help="Minimum failure rate for a weak group (default: 0.5)",
    )
    recommend_parser.add_argument(
        "--min-samples", type=positive_int, default=1,
        help="Minimum historical records per group (default: 1)",
    )
    recommend_parser.add_argument(
        "--limit", type=positive_int, default=20,
        help="Maximum recommended problems (default: 20)",
    )
    recommend_parser.add_argument("--log-format", choices=["console", "json"], default="console")

    ab_parser = subparsers.add_parser("ab-test", help="Run a two-variant prompt A/B test")
    ab_parser.add_argument("--config", required=True, help="A/B test JSON or YAML configuration")
    ab_parser.add_argument("--output-dir", help="Override configured output directory")
    ab_parser.add_argument("--log-format", choices=["console", "json"], default="console")

    # Benchmark command for learning curve tracking
    benchmark_parser = subparsers.add_parser(
        "benchmark", help="Run benchmark evaluation for learning curve tracking"
    )
    benchmark_parser.add_argument(
        "--suite", type=str, help="Path to benchmark suite configuration file"
    )
    benchmark_parser.add_argument(
        "--list-suites", action="store_true", help="List available benchmark suites"
    )
    benchmark_parser.add_argument(
        "--compare", action="store_true", help="Enable multi-model comparison mode"
    )
    benchmark_parser.add_argument("--output", type=str, help="Output path for report")
    benchmark_parser.add_argument(
        "--log-format", choices=["console", "json"], default="console"
    )

    # Tag management commands
    tags_parser = subparsers.add_parser("tags", help="Normalize and recommend problem tags")
    tags_subparsers = tags_parser.add_subparsers(dest="tags_command", required=True)
    normalize_tags_parser = tags_subparsers.add_parser(
        "normalize", help="Preview or write canonical tags for a dataset"
    )
    normalize_tags_parser.add_argument("--dataset", required=True, help="Problem dataset JSON path")
    normalize_tags_parser.add_argument(
        "--mapping", default=None, help="Custom tag mapping YAML (default: config/tag_mapping.yaml)"
    )
    normalize_tags_parser.add_argument(
        "--output", help="Write a normalized dataset to this path; input is never overwritten"
    )
    normalize_tags_parser.add_argument(
        "--report", help="Write the JSON normalization report to this path"
    )
    normalize_tags_parser.add_argument(
        "--apply-recommendations",
        action="store_true",
        help="Include suggested tags in --output after user review",
    )
    normalize_tags_parser.add_argument(
        "--min-confidence",
        type=confidence_threshold,
        default=0.8,
        help="Minimum keyword confidence for suggestions (default: 0.8)",
    )

    # Debug command
    from harness.cli.debug import add_debug_subcommand
    add_debug_subcommand(subparsers)

    # Cache command
    cache_parser = subparsers.add_parser(
        "cache", help="Manage LLM response cache"
    )
    cache_subparsers = cache_parser.add_subparsers(dest="cache_action", help="Cache actions")

    # cache clear
    clear_parser = cache_subparsers.add_parser("clear", help="Clear cache entries")
    clear_parser.add_argument(
        "--model",
        type=str,
        help="Clear only entries for the specified model",
    )

    # cache stats
    stats_parser = cache_subparsers.add_parser("stats", help="Show cache statistics")

    cache_parser.add_argument(
        "--log-format", choices=["console", "json"], default="console"
    )

    # Subcommand dispatch: `run` (default), `import`, `experiment`, `optimize`,
    # `recommend`, `ab-test`, `benchmark`, `tags`, `debug`, and `cache`. Bare invocation without a subcommand is parsed
    # directly by the run parser so legacy flag-only command lines keep working.
    argv = sys.argv[1:]
    if argv and argv[0] in (
        "run",
        "import",
        "experiment",
        "optimize",
        "recommend",
        "ab-test",
        "benchmark",
        "tags",
        "debug",
        "cache",
    ):
        args = parser.parse_args(argv)
    else:
        args = run_parser.parse_args(argv)
        args.command = "run"

    # Handle import command
    if args.command == "import":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_import_command(args)
        sys.exit(exit_code)

    # Handle experiment command
    if args.command == "experiment":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_experiment_command(args)
        sys.exit(exit_code)

    # Handle optimize command
    if args.command == "optimize":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_optimize_command(args)
        sys.exit(exit_code)

    # Handle recommend command
    if args.command == "recommend":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_recommend_command(args)
        sys.exit(exit_code)

    if args.command == "ab-test":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_ab_test_command(args)
        sys.exit(exit_code)

    # Handle benchmark command
    if args.command == "benchmark":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_benchmark_command(args)
        sys.exit(exit_code)

    if args.command == "tags":
        setup_logging(console_format="console")
        if args.tags_command == "normalize":
            exit_code = run_tags_normalize_command(args)
            sys.exit(exit_code)

    # Handle debug command
    if args.command == "debug":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        from harness.cli.debug import run_debug_command
        exit_code = run_debug_command(args)
        sys.exit(exit_code)

    # Handle cache command
    if args.command == "cache":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        if not hasattr(args, "cache_action") or args.cache_action is None:
            parser.error("cache command requires an action (clear, stats)")
        exit_code = run_cache_command(args)
        sys.exit(exit_code)

    setup_logging(console_format=args.log_format)

    # Execute run command
    if args.command == "run":
        try:
            # Load or create config
            if args.config:
                config = load_config(args.config, overrides=config_file_overrides(args))
                logger.info("config_loaded", path=args.config)
            else:
                if not args.dataset:
                    parser.error("--dataset is required when --config is not provided")
                config = create_default_config(args.dataset, args.output or "./results")
                logger.info("using_default_config")

            # Provider introspection commands: use the free listing endpoint and
            # exit before any evaluation runs. Placed before apply_cli_overrides so
            # strategy/dataset overrides cannot block pure query commands
            if args.list_models or args.check_connection:
                client = LLMClient(config.llm_config)

                if args.check_connection:
                    status = client.check_connection()
                    if status["ok"]:
                        print(
                            f"Connection OK: provider={status['provider']} "
                            f"base_url={status['base_url']} models={status['model_count']}"
                        )
                        print(
                            "Note: this check used the free model listing endpoint; "
                            "a generation-based check would incur billing."
                        )
                    else:
                        print(f"Connection failed: {status['error']}")
                        print(
                            "Fix the credentials/network above, or configure a model ID "
                            "manually in your config (llm_config.model) and run the evaluation."
                        )
                        sys.exit(1)

                if args.list_models:
                    try:
                        models = client.list_models()
                    except Exception as e:
                        print(f"Model listing failed: {e}")
                        print(
                            "You can still configure the model ID manually in your config "
                            "(llm_config.model) and run the evaluation."
                        )
                        sys.exit(1)
                    print(f"Available models ({len(models)}):")
                    for model_id in models:
                        print(f"  - {model_id}")
                    print(
                        "Note: model size metadata is not reliably provided by the listing "
                        "API and is shown as unknown."
                    )

                return

            config = apply_cli_overrides(config, args)

            # Initialize and run harness
            logger.info("harness_starting")
            harness = AlgorithmHarness(config)
            reports = harness.run(use_task_service=True, run_id=args.run_id, resume=args.resume)

            # Print and save results
            print_report(reports)
            save_results(reports, config.output_dir, harness, config)

            if config.budget_cap_usd is not None or config.difficulty_strategy:
                snapshot = harness.cost_monitor.snapshot()
                cap_text = (
                    f"${snapshot['budget_cap_usd']}"
                    if snapshot["budget_cap_usd"] is not None
                    else "no cap"
                )
                print(
                    f"Cost control: accumulated ${snapshot['accumulated_cost_usd']:.4f} "
                    f"of {cap_text}; "
                    f"{snapshot['downgraded_problems']} problem(s) downgraded; "
                    f"{snapshot['unknown_usage_results']} result(s) with unknown usage "
                    "not counted toward the cap"
                )
                if harness.task_record is not None and harness.task_record.state == "paused":
                    print("Evaluation paused at budget cap; see cost_cutoff.json in the run output.")

            logger.info("harness_completed")

        except FileNotFoundError as e:
            logger.error("file_not_found", error=str(e))
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        except Exception as e:
            logger.error("harness_failed", error=str(e))
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
