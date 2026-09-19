"""
Main entry point for LLM Algorithm Harness.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.harness import AlgorithmHarness
from src.llm_client import LLMClient
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
        print(
            "  Formal Hidden Evaluation: "
            f"{report.formal_solved_problems}/{report.formal_evaluable_problems} "
            f"({report.formal_success_rate:.2%})"
        )
        print(f"  Sample-only Problems: {report.sample_only_problems}")
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


def run_import_command(args: argparse.Namespace) -> int:
    """
    Execute the import command.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure, 3=strict mode failure)
    """
    from src.importers.base import ImportResult
    from src.importers.leetcode import LeetCodeImporter
    from src.importers.livecodebench import LiveCodeBenchImporter
    from src.importers.local_json import LocalJsonImporter
    from src.importers.mock import MockPlatformImporter
    from src.problem_loader import ProblemLoader

    # Map source type to importer class
    IMPORTERS = {
        "local-json": LocalJsonImporter,
        "leetcode": LeetCodeImporter,
        "livecodebench": LiveCodeBenchImporter,
        "mock": MockPlatformImporter,
    }

    if args.source not in IMPORTERS:
        print(f"Error: --source is required. Supported types: {', '.join(IMPORTERS.keys())}", file=sys.stderr)
        return 2

    try:
        # Instantiate importer
        importer_class = IMPORTERS[args.source]
        if args.source == "livecodebench":
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
        logger.info("import_starting", source=args.source, input=args.input)
        raw_data = importer.fetch_problems(args.input)
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
        print(f"  New problems to import: {len([p for p in valid_problems if p.problem_id not in skipped_ids and p.problem_id not in overwritten_ids])}")
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
            if response.lower() != 'y':
                print("Import cancelled.")
                return 0

        # Persist (unless preview mode)
        if not args.preview:
            importer.persist_dataset(final_problems, args.output)
            print(f"Dataset written to: {args.output}")
        else:
            print("No changes were made to the dataset (preview mode).")

        # Generate and display report
        report = importer.generate_report(result, args.input, args.output, args.preview)
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
    import_parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Import source type (e.g., local-json, leetcode, mock)",
    )
    import_parser.add_argument(
        "--input",
        type=str,
        required=True,
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
    import_parser.add_argument(
        "--log-format",
        choices=["console", "json"],
        default="console",
        help="Terminal log rendering",
    )

    # Subcommand dispatch: `run` (default) and `import`. Bare invocation
    # without a subcommand is parsed directly by the run parser so legacy
    # flag-only command lines keep working.
    argv = sys.argv[1:]
    if argv and argv[0] in ("run", "import"):
        args = parser.parse_args(argv)
    else:
        args = run_parser.parse_args(argv)
        args.command = "run"

    # Handle import command
    if args.command == "import":
        setup_logging(console_format=getattr(args, "log_format", "console"))
        exit_code = run_import_command(args)
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
