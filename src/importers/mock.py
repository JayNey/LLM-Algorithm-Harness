"""
Mock platform importer for testing and examples.
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple

from src.importers.base import ImportResult, ProblemImporter
from src.models import Problem, TestCase
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MockPlatformImporter(ProblemImporter):
    """
    Mock importer for testing and demonstration purposes.

    Generates synthetic test problems instead of fetching from a real source.
    """

    def fetch_problems(self, source: str) -> Any:
        """
        Generate mock problem data.

        Args:
            source: Ignored for mock importer (use count, e.g., "5")

        Returns:
            List of mock problem dictionaries
        """
        try:
            count = int(source)
        except ValueError:
            count = 3

        logger.info("fetching_mock_problems", count=count)

        problems = []
        for i in range(count):
            problem = {
                "problem_id": f"mock-{i+1:03d}",
                "title": f"Mock Problem {i+1}",
                "description": f"This is a mock problem generated for testing. Problem number {i+1}.",
                "difficulty": ["easy", "medium", "hard"][i % 3],
                "tags": ["mock", "testing"],
                "constraints": "1 <= n <= 100",
                "source_platform": "mock",
                "source_problem_id": f"{i+1:03d}",
                "input_output_mode": "function",
                "entry_point": "solution(**test_input)",
                "public_test_cases": [
                    {
                        "input": {"n": 1},
                        "expected_output": 1,
                        "source": "public",
                    },
                    {
                        "input": {"n": 2},
                        "expected_output": 2,
                        "source": "public",
                    },
                ],
            }
            problems.append(problem)

        return problems

    def transform_to_schema(self, raw_data: Any) -> List[Problem]:
        """
        Transform mock data to Problem objects.

        Args:
            raw_data: List of problem dictionaries

        Returns:
            List of Problem objects
        """
        problems = []
        for item in raw_data:
            try:
                problem = Problem(**item)
                problems.append(problem)
            except Exception as e:
                logger.warning("mock_problem_transform_failed", error=str(e))

        logger.info("mock_problems_transformed", count=len(problems))
        return problems

    def detect_duplicates(
        self, problems: List[Problem], existing_problems: List[Problem], update_strategy: str
    ) -> Tuple[List[Problem], List[str], List[str]]:
        """
        Detect and handle duplicates (reuses base logic via composition).

        Args:
            problems: New problems
            existing_problems: Existing problems
            update_strategy: 'skip' or 'overwrite'

        Returns:
            Tuple of (final_problems, skipped_ids, overwritten_ids)
        """
        # Use same logic as LocalJsonImporter
        existing_map: Dict[Tuple[str, str], Problem] = {}
        for p in existing_problems:
            key = (p.source_platform, p.source_problem_id or p.problem_id)
            existing_map[key] = p

        final_problems = list(existing_problems)
        skipped_ids = []
        overwritten_ids = []

        for problem in problems:
            key = (problem.source_platform, problem.source_problem_id or problem.problem_id)

            if key in existing_map:
                if update_strategy == "overwrite":
                    old_problem = existing_map[key]
                    final_problems.remove(old_problem)
                    final_problems.append(problem)
                    overwritten_ids.append(problem.problem_id)
                else:
                    skipped_ids.append(problem.problem_id)
            else:
                final_problems.append(problem)

        return final_problems, skipped_ids, overwritten_ids

    def generate_report(
        self, result: ImportResult, source: str, output_path: str, preview: bool
    ) -> Dict[str, Any]:
        """
        Generate mock import report.

        Args:
            result: Import result
            source: Source identifier
            output_path: Output path
            preview: Preview mode flag

        Returns:
            Report dictionary
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "source": "mock",
            "input_path": source,
            "output_path": output_path,
            "preview_mode": preview,
            "summary": {
                "total_attempted": result.total_attempted,
                "successful": len(result.successful),
                "failed": len(result.failed),
                "duplicates_skipped": len(result.duplicates_skipped),
                "duplicates_overwritten": len(result.duplicates_overwritten),
            },
            "successful_problems": [p.problem_id for p in result.successful],
            "failed_problems": result.failed,
            "duplicates": [
                {"problem_id": pid, "action": "skipped"} for pid in result.duplicates_skipped
            ]
            + [
                {"problem_id": pid, "action": "overwritten"}
                for pid in result.duplicates_overwritten
            ],
        }
