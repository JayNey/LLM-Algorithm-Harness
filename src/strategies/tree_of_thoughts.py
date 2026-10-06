"""Tree of Thoughts strategy: explore multiple reasoning paths through search."""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from src.budget import BudgetExhausted
from src.models import ExecutionResult, IterationResult, Problem, StrategyConfig
from src.strategy_base import StrategyBase
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.llm_client import LLMClient
    from src.sandbox_executor import SandboxExecutor

logger = get_logger(__name__)


@dataclass
class ThoughtNode:
    """Represents a node in the tree of thoughts."""

    depth: int
    thought: str
    code_snippet: str
    quality_score: float
    parent: ThoughtNode | None = None
    children: list[ThoughtNode] = field(default_factory=list)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"ThoughtNode(depth={self.depth}, "
            f"quality_score={self.quality_score:.3f}, "
            f"thought={self.thought[:50]}..., "
            f"children={len(self.children)})"
        )


class TreeOfThoughtsStrategy(StrategyBase):
    """
    Tree of Thoughts strategy: explore multiple reasoning branches.

    Generates multiple candidate solutions at each step, evaluates their quality,
    and prunes low-quality branches to focus computational resources on promising paths.
    """

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
        branching_factor: int = 3,
        max_depth: int = 4,
        search_strategy: Literal["bfs", "dfs"] = "bfs",
        pruning_threshold: float = 0.3,
    ):
        """
        Initialize Tree of Thoughts strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client for generation
            sandbox: Sandbox executor for testing
            branching_factor: Number of branches to generate at each node (must be >= 1)
            max_depth: Maximum depth of the search tree (must be >= 1)
            search_strategy: Search algorithm to use ("bfs" or "dfs")
            pruning_threshold: Minimum quality score to keep a branch (0.0 to 1.0)

        Raises:
            ValueError: If any parameter is invalid
        """
        super().__init__(config, llm_client, sandbox)

        if branching_factor < 1:
            raise ValueError(f"branching_factor must be >= 1, got {branching_factor}")
        if max_depth < 1:
            raise ValueError(f"max_depth must be >= 1, got {max_depth}")
        if search_strategy not in ("bfs", "dfs"):
            raise ValueError(f"search_strategy must be 'bfs' or 'dfs', got '{search_strategy}'")
        if not 0.0 <= pruning_threshold <= 1.0:
            raise ValueError(
                f"pruning_threshold must be between 0.0 and 1.0, got {pruning_threshold}"
            )

        self.branching_factor = branching_factor
        self.max_depth = max_depth
        self.search_strategy = search_strategy
        self.pruning_threshold = pruning_threshold

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute Tree of Thoughts strategy on the given problem.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult containing the best solution found
        """
        self.logger.info(
            "executing_tree_of_thoughts_strategy",
            problem_id=problem.problem_id,
            branching_factor=self.branching_factor,
            max_depth=self.max_depth,
            search_strategy=self.search_strategy,
        )
        started = time.perf_counter()

        # Create root node
        root = self.create_root_node(problem)

        # Search the tree
        result = self.search_tree(root, problem)

        elapsed = time.perf_counter() - started
        self.logger.info(
            "tree_of_thoughts_complete",
            problem_id=problem.problem_id,
            elapsed=elapsed,
            success=result.success,
        )

        return result

    def create_root_node(self, problem: Problem) -> ThoughtNode:
        """
        Create the root node for the search tree.

        Args:
            problem: Problem to solve

        Returns:
            Root ThoughtNode at depth 0
        """
        root_thought = f"Analyzing problem: {problem.problem_id}"
        return ThoughtNode(
            depth=0,
            thought=root_thought,
            code_snippet="",
            quality_score=1.0,  # Root starts with perfect score
            parent=None,
            children=[],
        )

    def generate_branches(self, node: ThoughtNode, problem: Problem) -> list[ThoughtNode]:
        """
        Generate multiple child branches from a given node.

        Args:
            node: Parent node to expand
            problem: Problem being solved

        Returns:
            List of child ThoughtNodes (may be empty if all pruned or generation fails)
        """
        # Construct prompt to generate multiple reasoning branches
        prompt = self._build_branch_generation_prompt(node, problem)

        try:
            self._before_generate(prompt)
            llm_response = self.generate(prompt)
        except BudgetExhausted:
            self.logger.warning("budget_exhausted_during_branch_generation")
            return []

        # Parse the response to extract multiple branches
        branches = self._parse_branches_from_response(llm_response.text, node)

        self.logger.info(
            "generated_branches",
            parent_depth=node.depth,
            requested=self.branching_factor,
            generated=len(branches),
        )

        return branches

    def _build_branch_generation_prompt(self, node: ThoughtNode, problem: Problem) -> str:
        """
        Build prompt for generating multiple reasoning branches.

        Args:
            node: Current node
            problem: Problem being solved

        Returns:
            Prompt string for LLM
        """
        base_prompt = self.build_base_prompt(problem)

        if node.depth == 0:
            # Root node - generate initial approaches
            prompt = f"""{base_prompt}

Generate {self.branching_factor} different approaches to solve this problem.
For each approach, provide:
1. A brief reasoning about why this approach might work
2. A code implementation

Format your response as:
=== Approach 1 ===
Reasoning: [your reasoning here]
Code:
```python
[your code here]
```

=== Approach 2 ===
Reasoning: [your reasoning here]
Code:
```python
[your code here]
```

... continue for all {self.branching_factor} approaches.
"""
        else:
            # Non-root node - explore variations
            prompt = f"""{base_prompt}

Current reasoning path:
{node.thought}

Current code:
```python
{node.code_snippet}
```

Generate {self.branching_factor} different ways to refine or continue this approach.
For each variation, provide:
1. A brief reasoning about the refinement
2. Updated code implementation

Format your response as:
=== Variation 1 ===
Reasoning: [your reasoning here]
Code:
```python
[your code here]
```

=== Variation 2 ===
Reasoning: [your reasoning here]
Code:
```python
[your code here]
```

... continue for all {self.branching_factor} variations.
"""

        return prompt

    def _parse_branches_from_response(
        self, response_text: str, parent: ThoughtNode
    ) -> list[ThoughtNode]:
        """
        Parse LLM response to extract multiple branches.

        Args:
            response_text: Raw LLM response
            parent: Parent node

        Returns:
            List of ThoughtNode children
        """
        branches = []

        # Split response by approach/variation markers
        sections = re.split(r"===\s*(?:Approach|Variation)\s+\d+\s*===", response_text)

        for section in sections[1:]:  # Skip first empty section
            if not section.strip():
                continue

            # Extract reasoning
            reasoning_match = re.search(r"Reasoning:\s*(.+?)(?=Code:|$)", section, re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else "Refinement"

            # Extract code using existing extract_code method
            code = self.extract_code(section, problem=None)
            if not code:
                continue

            # Create child node
            child = ThoughtNode(
                depth=parent.depth + 1,
                thought=reasoning,
                code_snippet=code,
                quality_score=0.0,  # Will be evaluated later
                parent=parent,
                children=[],
            )
            branches.append(child)

            # Stop if we have enough branches
            if len(branches) >= self.branching_factor:
                break

        return branches

    def evaluate_node(self, node: ThoughtNode, problem: Problem) -> float:
        """
        Evaluate the quality of a thought node.

        Args:
            node: Node to evaluate
            problem: Problem being solved

        Returns:
            Quality score between 0.0 and 1.0
        """
        prompt = self._build_evaluation_prompt(node, problem)

        try:
            llm_response = self.generate(prompt)
            score = self._parse_quality_score(llm_response.text)
        except BudgetExhausted:
            self.logger.warning("budget_exhausted_during_evaluation")
            score = 0.5  # Default to neutral score
        except Exception as e:
            self.logger.warning("evaluation_failed", error=str(e))
            score = 0.5  # Default to neutral score

        # Ensure score is bounded
        score = max(0.0, min(1.0, score))

        self.logger.info(
            "evaluated_node",
            depth=node.depth,
            quality_score=score,
        )

        return score

    def _build_evaluation_prompt(self, node: ThoughtNode, problem: Problem) -> str:
        """
        Build prompt for evaluating node quality.

        Args:
            node: Node to evaluate
            problem: Problem being solved

        Returns:
            Evaluation prompt string
        """
        base_prompt = self.build_base_prompt(problem)

        prompt = f"""{base_prompt}

Evaluate the following approach and code solution:

Reasoning:
{node.thought}

Code:
```python
{node.code_snippet}
```

Rate this solution on a scale from 0.0 to 1.0 based on:
- Logical correctness of the reasoning
- Code quality and completeness
- Likelihood of solving the problem correctly

Respond with ONLY a number between 0.0 and 1.0, nothing else.
Example: 0.75
"""

        return prompt

    def _parse_quality_score(self, response_text: str) -> float:
        """
        Parse quality score from LLM response.

        Args:
            response_text: Raw LLM response

        Returns:
            Quality score between 0.0 and 1.0

        Raises:
            ValueError: If no valid score found
        """
        # Look for a float number in the response
        matches = re.findall(r"\b0?\.\d+\b|\b1\.0+\b|\b[01]\b", response_text)

        if not matches:
            raise ValueError(f"No quality score found in response: {response_text[:100]}")

        # Take the first match
        score = float(matches[0])

        # Ensure it's bounded
        return max(0.0, min(1.0, score))

    def prune_branches(self, branches: list[ThoughtNode]) -> list[ThoughtNode]:
        """
        Prune low-quality branches based on pruning threshold.

        Args:
            branches: List of branches to filter

        Returns:
            List of branches that pass the quality threshold
        """
        kept = [b for b in branches if b.quality_score >= self.pruning_threshold]
        pruned = len(branches) - len(kept)

        if pruned > 0:
            self.logger.info(
                "pruned_branches",
                total=len(branches),
                pruned=pruned,
                kept=len(kept),
                threshold=self.pruning_threshold,
            )

        return kept

    def search_tree(self, root: ThoughtNode, problem: Problem) -> ExecutionResult:
        """
        Search the thought tree to find the best solution.

        Args:
            root: Root node of the tree
            problem: Problem being solved

        Returns:
            ExecutionResult with the best solution found
        """
        start_time = time.perf_counter()
        iterations = []
        all_nodes = [root]

        # Initialize search queue/stack
        if self.search_strategy == "bfs":
            queue = deque([root])
        else:  # dfs
            stack = [root]

        nodes_explored = 0

        try:
            while (self.search_strategy == "bfs" and queue) or (
                self.search_strategy == "dfs" and stack
            ):
                # Get next node to expand
                if self.search_strategy == "bfs":
                    current = queue.popleft()
                else:
                    current = stack.pop()

                nodes_explored += 1

                # Skip if at max depth
                if current.depth >= self.max_depth:
                    continue

                # Generate branches
                iteration_start = time.perf_counter()
                branches = self.generate_branches(current, problem)

                if not branches:
                    continue

                # Evaluate each branch
                for branch in branches:
                    branch.quality_score = self.evaluate_node(branch, problem)

                # Prune low-quality branches
                kept_branches = self.prune_branches(branches)

                # Add kept branches to parent's children
                current.children.extend(kept_branches)
                all_nodes.extend(kept_branches)

                # Add to search queue/stack
                if self.search_strategy == "bfs":
                    queue.extend(kept_branches)
                else:
                    stack.extend(reversed(kept_branches))  # Reverse for DFS order

                # Record iteration
                iteration_elapsed = time.perf_counter() - iteration_start
                iteration = IterationResult(
                    iteration=nodes_explored,
                    code_extracted=current.code_snippet,
                )
                iterations.append(iteration)

        except BudgetExhausted as e:
            self.logger.warning("budget_exhausted_during_search", nodes_explored=nodes_explored)
            # Continue to extract best solution from explored nodes

        elapsed_time = time.perf_counter() - start_time

        # Extract best solution from all explored nodes
        return self._extract_best_solution(all_nodes, iterations, problem, elapsed_time)

    def _extract_best_solution(
        self,
        all_nodes: list[ThoughtNode],
        iterations: list[IterationResult],
        problem: Problem,
        elapsed_time: float,
    ) -> ExecutionResult:
        """
        Extract the best solution from explored nodes.

        Args:
            all_nodes: All nodes explored during search
            iterations: Iteration history
            problem: Problem being solved
            elapsed_time: Total elapsed time in seconds

        Returns:
            ExecutionResult with the best solution
        """
        # Find leaf nodes (nodes with no children or at max depth)
        leaf_nodes = [
            node for node in all_nodes if not node.children or node.depth >= self.max_depth
        ]

        if not leaf_nodes:
            return self.create_execution_result(
                problem=problem,
                iterations=iterations,
                final_result=None,
                success=False,
                llm_responses=[],
                failure_category="code_extraction_failed",
                execution_time_seconds=elapsed_time,
            )

        # Find the leaf with highest quality score
        best_leaf = max(leaf_nodes, key=lambda n: n.quality_score)

        self.logger.info(
            "best_solution_found",
            depth=best_leaf.depth,
            quality_score=best_leaf.quality_score,
            total_nodes=len(all_nodes),
            leaf_nodes=len(leaf_nodes),
        )

        # Test the best solution
        sandbox_result = None
        success = False
        if best_leaf.code_snippet:
            try:
                if problem.public_test_cases:
                    sandbox_result = self.sandbox.execute(
                        best_leaf.code_snippet, problem, stage="public"
                    )
                    success = sandbox_result.all_passed
                elif problem.feedback_test_cases:
                    sandbox_result = self.sandbox.execute(
                        best_leaf.code_snippet, problem, stage="feedback"
                    )
                    success = sandbox_result.all_passed
                else:
                    # Hidden-only problems
                    success = True
            except Exception as e:
                self.logger.error("sandbox_execution_failed", error=str(e))

        return self.create_execution_result(
            problem=problem,
            iterations=iterations,
            final_result=sandbox_result,
            success=success,
            llm_responses=[],
            execution_time_seconds=elapsed_time,
        )
