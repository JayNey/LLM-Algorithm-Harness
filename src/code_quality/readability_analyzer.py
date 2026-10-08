"""
Readability Analyzer

Analyzes code readability through:
- pylint integration for quality scoring
- flake8 for style checking
- radon for cyclomatic complexity
"""

import subprocess
import tempfile
from pathlib import Path

from src.code_quality.models import ReadabilityScore
from src.utils.encoding import utf8_subprocess_env
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReadabilityAnalyzer:
    """Analyzes code readability using static analysis tools."""

    def analyze(self, code: str) -> ReadabilityScore:
        """
        Analyze code readability.

        Args:
            code: Python code to analyze

        Returns:
            ReadabilityScore with analysis results
        """
        try:
            pylint_score = self._run_pylint(code)
            flake8_issues = self._run_flake8(code)
            complexity = self._run_radon(code)

            # Calculate overall readability score
            readability = self._calculate_readability_score(pylint_score, flake8_issues, complexity)

            return ReadabilityScore(
                pylint_score=pylint_score,
                flake8_issues=flake8_issues,
                cyclomatic_complexity=complexity,
                max_function_complexity=None,
                readability_score=readability,
                issues=[],
            )

        except Exception as e:
            logger.warning("readability_analysis_failed", error=str(e))
            return ReadabilityScore(
                pylint_score=None,
                flake8_issues=None,
                cyclomatic_complexity=None,
                max_function_complexity=None,
                readability_score=None,
                issues=[],
            )

    def _run_pylint(self, code: str) -> float | None:
        """Run pylint and extract score."""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                ["pylint", temp_path, "--score=y"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                env=utf8_subprocess_env(),
            )

            # Parse score from output
            for line in result.stdout.splitlines():
                if "rated at" in line.lower():
                    parts = line.split("/")
                    if parts:
                        score_str = parts[0].split()[-1]
                        return float(score_str)

            return None

        except Exception as e:
            logger.debug("pylint_failed", error=str(e))
            return None
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

    def _run_flake8(self, code: str) -> int | None:
        """Run flake8 and count issues."""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                ["flake8", temp_path],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                env=utf8_subprocess_env(),
            )

            issue_count = len([line for line in result.stdout.splitlines() if line.strip()])
            return issue_count

        except Exception as e:
            logger.debug("flake8_failed", error=str(e))
            return None
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

    def _run_radon(self, code: str) -> float | None:
        """Run radon and get cyclomatic complexity."""
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                ["radon", "cc", temp_path, "-s"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                env=utf8_subprocess_env(),
            )

            # Parse average complexity
            for line in result.stdout.splitlines():
                if "Average complexity:" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        return float(parts[1].strip().split()[0])

            return None

        except Exception as e:
            logger.debug("radon_failed", error=str(e))
            return None
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

    def _calculate_readability_score(
        self,
        pylint_score: float | None,
        flake8_issues: int | None,
        complexity: float | None,
    ) -> float | None:
        """Calculate overall readability score (0-100)."""
        scores = []

        if pylint_score is not None:
            scores.append(pylint_score * 10)  # Convert 0-10 to 0-100

        if flake8_issues is not None:
            # Fewer issues = better score
            flake8_score = max(0, 100 - (flake8_issues * 5))
            scores.append(flake8_score)

        if complexity is not None:
            # Lower complexity = better score
            complexity_score = max(0, 100 - (complexity * 10))
            scores.append(complexity_score)

        if not scores:
            return None

        return round(sum(scores) / len(scores), 2)
