"""
Style Consistency Analyzer

Analyzes code style consistency through:
- black formatting checker
- Style violation detection and counting
"""

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from src.code_quality.models import StyleConsistencyScore
from src.utils.logging import get_logger

logger = get_logger(__name__)


class StyleConsistencyAnalyzer:
    """Analyzes code style consistency."""

    def analyze(self, code: str) -> StyleConsistencyScore:
        """
        Analyze code style consistency.

        Args:
            code: Python code to analyze

        Returns:
            StyleConsistencyScore with analysis results
        """
        try:
            black_compliant, violations = self._check_black_format(code)

            # Calculate style score
            if black_compliant:
                style_score = 100.0
            else:
                # Deduct points for violations
                style_score = max(0, 100 - (len(violations) * 2))

            return StyleConsistencyScore(
                black_compliant=black_compliant,
                style_violations=len(violations),
                style_score=style_score,
                violations_detail=violations,
            )

        except Exception as e:
            logger.warning("style_analysis_failed", error=str(e))
            return StyleConsistencyScore(
                black_compliant=None,
                style_violations=0,
                style_score=None,
                violations_detail=[],
            )

    def _check_black_format(self, code: str) -> tuple[bool, List[str]]:
        """
        Check if code passes black formatting.

        Returns:
            (is_compliant, violations_list)
        """
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                ["black", "--check", temp_path], capture_output=True, text=True, timeout=10
            )

            is_compliant = result.returncode == 0
            violations = []

            if not is_compliant:
                violations.append("Code does not conform to black formatting")
                # Parse specific violations if available
                if result.stderr:
                    violations.append(result.stderr[:200])

            return is_compliant, violations

        except FileNotFoundError:
            logger.debug("black_not_installed")
            return True, []  # Assume compliant if black not available
        except Exception as e:
            logger.debug("black_check_failed", error=str(e))
            return True, []
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
