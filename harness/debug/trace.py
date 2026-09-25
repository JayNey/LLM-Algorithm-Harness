"""
Trace recording and visualization for interactive debugging.
"""

import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict, field


@dataclass
class RoundTrace:
    """Record of a single execution round."""

    round: int
    prompt: str
    response: Optional[str] = None
    code: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None
    user_interventions: List[Dict[str, str]] = field(default_factory=list)
    status: str = "pending"  # pending, passed, failed, error


class TraceRecorder:
    """Records and displays execution traces for debugging sessions."""

    def __init__(self, problem_id: str, strategy_name: str, model_name: str):
        """
        Initialize trace recorder.

        Args:
            problem_id: ID of the problem being debugged
            strategy_name: Name of the strategy being used
            model_name: Name of the LLM model
        """
        self.problem_id = problem_id
        self.strategy_name = strategy_name
        self.model_name = model_name
        self.rounds: List[RoundTrace] = []
        self._current_round: Optional[RoundTrace] = None

    def start_round(self, round_number: int, prompt: str) -> None:
        """
        Start recording a new round.

        Args:
            round_number: Round number
            prompt: The prompt for this round
        """
        self._current_round = RoundTrace(round=round_number, prompt=prompt)

    def record_response(self, response: str) -> None:
        """Record LLM response for current round."""
        if self._current_round:
            self._current_round.response = response

    def record_code(self, code: str) -> None:
        """Record extracted code for current round."""
        if self._current_round:
            self._current_round.code = code

    def record_execution(self, result: Dict[str, Any]) -> None:
        """Record execution result for current round."""
        if self._current_round:
            self._current_round.execution_result = result

    def record_feedback(self, feedback: str) -> None:
        """Record feedback for current round."""
        if self._current_round:
            self._current_round.feedback = feedback

    def record_intervention(self, intervention_type: str, details: str) -> None:
        """
        Record user intervention.

        Args:
            intervention_type: Type of intervention (edit_prompt, set_param, inject, etc.)
            details: Details of the intervention
        """
        if self._current_round:
            self._current_round.user_interventions.append({
                "type": intervention_type,
                "details": details,
            })

    def complete_round(self, status: str) -> None:
        """
        Complete the current round.

        Args:
            status: Final status (passed, failed, error)
        """
        if self._current_round:
            self._current_round.status = status
            self.rounds.append(self._current_round)
            self._current_round = None

    def display_summary(self) -> str:
        """
        Display a summary of all rounds.

        Returns:
            Formatted summary string
        """
        if not self.rounds:
            return "No rounds recorded yet."

        lines = ["=" * 60]
        lines.append("Execution Trace Summary")
        lines.append("=" * 60)
        lines.append(f"Problem: {self.problem_id}")
        lines.append(f"Strategy: {self.strategy_name}")
        lines.append(f"Model: {self.model_name}")
        lines.append(f"Total Rounds: {len(self.rounds)}")
        lines.append("")

        for round_trace in self.rounds:
            status_symbol = {
                "passed": "✓",
                "failed": "✗",
                "error": "!",
                "pending": "?",
            }.get(round_trace.status, "?")

            action = "Generate"
            if round_trace.execution_result:
                action = "Execute"
            if round_trace.feedback:
                action = "Refine"

            interventions = (
                f" [+{len(round_trace.user_interventions)} interventions]"
                if round_trace.user_interventions
                else ""
            )

            lines.append(
                f"Round {round_trace.round}: {action} → {round_trace.status.upper()} {status_symbol}{interventions}"
            )

        lines.append("=" * 60)
        return "\n".join(lines)

    def display_round(self, round_number: int) -> str:
        """
        Display detailed information for a specific round.

        Args:
            round_number: Round number to display

        Returns:
            Formatted round details string
        """
        round_trace = next(
            (r for r in self.rounds if r.round == round_number), None
        )

        if not round_trace:
            return f"Round {round_number} not found."

        lines = ["=" * 60]
        lines.append(f"Round {round_trace.round} Details")
        lines.append("=" * 60)
        lines.append(f"Status: {round_trace.status.upper()}")
        lines.append("")

        lines.append("--- Prompt ---")
        lines.append(round_trace.prompt)
        lines.append("")

        if round_trace.response:
            lines.append("--- Response ---")
            lines.append(round_trace.response[:500] + ("..." if len(round_trace.response) > 500 else ""))
            lines.append("")

        if round_trace.code:
            lines.append("--- Code ---")
            lines.append(round_trace.code)
            lines.append("")

        if round_trace.execution_result:
            lines.append("--- Execution Result ---")
            lines.append(json.dumps(round_trace.execution_result, indent=2))
            lines.append("")

        if round_trace.feedback:
            lines.append("--- Feedback ---")
            lines.append(round_trace.feedback)
            lines.append("")

        if round_trace.user_interventions:
            lines.append("--- User Interventions ---")
            for intervention in round_trace.user_interventions:
                lines.append(f"  {intervention['type']}: {intervention['details']}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def export_json(self, filepath: str) -> bool:
        """
        Export trace to JSON file.

        Args:
            filepath: Path to save JSON file

        Returns:
            True if export succeeded, False otherwise
        """
        try:
            data = {
                "problem_id": self.problem_id,
                "strategy": self.strategy_name,
                "model": self.model_name,
                "total_rounds": len(self.rounds),
                "rounds": [asdict(r) for r in self.rounds],
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"Error exporting trace: {e}")
            return False

    def get_round_count(self) -> int:
        """Get the number of completed rounds."""
        return len(self.rounds)
