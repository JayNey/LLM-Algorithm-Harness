"""
Main entry point for LLM Algorithm Harness.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.harness import AlgorithmHarness
from src.models import HarnessConfig, LLMConfig, SandboxConfig, StrategyConfig
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
        print(f"  Avg Attempts: {report.avg_attempts_per_problem:.2f}")
        print(f"  Avg Tokens: {report.avg_tokens_per_problem:.0f}")
        print(f"  Estimated Cost: ${report.estimated_cost_usd:.4f}")
        print()


def create_run_dir(output_dir: str) -> Path:
    """
    Create a timestamped directory for this run's results.

    Args:
        output_dir: Base output directory

    Returns:
        Path to the created run directory
    """
    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_path = Path(output_dir) / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def save_results(reports: dict, output_dir: str, harness: AlgorithmHarness,
                 config: HarnessConfig):
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
    run_path = create_run_dir(output_dir)

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
    metadata_file = run_path / "metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info("metadata_saved", path=str(metadata_file))

    # Save summary report
    summary = redact_sensitive_data(
        {"strategies": {name: report.model_dump() for name, report in reports.items()}}
    )

    summary_file = run_path / "summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info("summary_saved", path=str(summary_file))

    # Save detailed results per strategy
    for strategy_name, results in harness.results.items():
        results_file = run_path / f"{strategy_name}_results.json"
        results_data = redact_sensitive_data([r.model_dump() for r in results])

        with open(results_file, "w") as f:
            json.dump(results_data, f, indent=2)

        logger.info("strategy_results_saved", strategy=strategy_name, path=str(results_file))

    # Update the latest-run pointer for tooling
    latest_file = Path(output_dir) / "latest.json"
    with open(latest_file, 'w') as f:
        json.dump({"latest_run": run_path.name}, f, indent=2)

    print(f"\nResults saved to: {run_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LLM Algorithm Harness - Evaluate LLM problem-solving strategies"
    )

    parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering: human-readable console (default) or machine-readable json",
    )

    parser.add_argument(
        "--dataset", type=str, help="Path to problem dataset JSON file (overrides config)"
    )

    parser.add_argument(
        "--config", type=str, help="Path to configuration JSON or YAML file (optional)"
    )

    parser.add_argument(
        "--output",
        "--output-dir",
        dest="output",
        type=str,
        help="Output directory for results (overrides config; default: ./results)",
    )

    parser.add_argument(
        "--strategy",
        type=str,
        choices=SUPPORTED_STRATEGIES,
        help="Run only specific strategy (optional, runs all by default)",
    )

    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Filter problems by difficulty (overrides config)",
    )

    parser.add_argument(
        "--tags",
        nargs="+",
        help="Filter problems by one or more tags (overrides config)",
    )

    parser.add_argument(
        "--limit",
        type=positive_int,
        help="Limit number of problems to evaluate; must be positive (overrides config)",
    )

    args = parser.parse_args()

    setup_logging(console_format=args.log_format)

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

        config = apply_cli_overrides(config, args)

        # Initialize and run harness
        logger.info("harness_starting")
        harness = AlgorithmHarness(config)
        reports = harness.run()

        # Print and save results
        print_report(reports)
        save_results(reports, config.output_dir, harness, config)

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
