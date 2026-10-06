"""
Few-Shot Learning strategy - Learn from similar solved problems.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.budget import BudgetExhausted
from src.llm_client import LLMClient
from src.models import ExecutionResult, Problem, StrategyConfig
from src.sandbox_executor import SandboxExecutor
from src.strategies.similarity.tag_based import calculate_tag_similarity
from src.strategy_base import StrategyBase


@dataclass
class ExampleProblem:
    """Lightweight problem representation for few-shot examples."""

    problem_id: str
    title: str
    description: str
    difficulty: str
    tags: list[str]


@dataclass
class SimilarProblem:
    """Similar problem with its solution."""

    problem: ExampleProblem
    solution_code: str
    similarity_score: float
    matching_tags: list[str]


class FewShotLearningStrategy(StrategyBase):
    """Few-Shot Learning strategy: solve problems using similar examples."""

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
    ):
        """
        Initialize Few-Shot Learning strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client
            sandbox: Sandbox executor
        """
        super().__init__(config, llm_client, sandbox)

        # Extract custom parameters
        custom_params = config.custom_params or {}
        self.num_examples = custom_params.get("num_examples", 3)
        self.similarity_metric = custom_params.get("similarity_metric", "tag_overlap")
        self.min_similarity_score = custom_params.get("min_similarity_score", 0.3)
        self.example_source = custom_params.get("example_source", "solved_problems")

        # Initialize example database
        self.example_db: list[SimilarProblem] = []
        self._load_example_database()

    def _load_example_database(self) -> None:
        """
        Load example database from evaluation results.

        Loads successfully solved problems and their solutions from
        project evaluation history.
        """
        self.logger.info("loading_example_database")

        # Try to load from results directory
        results_dir = Path("results")
        if not results_dir.exists():
            self.logger.warning("results_directory_not_found", path=str(results_dir))
            return

        loaded_count = 0

        # Scan for result files
        for result_file in results_dir.rglob("*_results.json"):
            try:
                with open(result_file, encoding="utf-8") as f:
                    results = json.load(f)

                # Extract successful solutions
                for result in results:
                    if result.get("status") == "success" and result.get("generated_code"):
                        # Try to load the problem
                        problem_id = result.get("problem_id")
                        if not problem_id:
                            continue

                        # Create a lightweight example problem
                        # Extract tags from result metadata if available
                        tags = result.get("tags", [])
                        if not tags and "problem_metadata" in result:
                            tags = result["problem_metadata"].get("tags", [])

                        problem = ExampleProblem(
                            problem_id=problem_id,
                            title=result.get("title", problem_id),
                            description=result.get("description", "Example problem from history"),
                            difficulty=result.get("difficulty", "medium"),
                            tags=tags,
                        )

                        try:
                            # We don't compute similarity yet - just store
                            self.example_db.append(
                                SimilarProblem(
                                    problem=problem,
                                    solution_code=result["generated_code"],
                                    similarity_score=0.0,  # Will be computed later
                                    matching_tags=[],
                                )
                            )
                            loaded_count += 1
                        except Exception as e:
                            self.logger.debug(
                                "failed_to_load_example",
                                problem_id=problem_id,
                                error=str(e),
                            )

            except Exception as e:
                self.logger.debug(
                    "failed_to_load_result_file",
                    file=str(result_file),
                    error=str(e),
                )

        self.logger.info(
            "example_database_loaded",
            total_examples=loaded_count,
        )

    def retrieve_similar(self, problem: Problem, k: int) -> list[SimilarProblem]:
        """
        Retrieve top-k similar problems from example database.

        Args:
            problem: Target problem
            k: Number of examples to retrieve

        Returns:
            List of similar problems sorted by similarity (highest first)
        """
        if not self.example_db:
            self.logger.info("no_examples_available")
            return []

        similarities = []

        for example in self.example_db:
            # Calculate similarity based on tags
            if self.similarity_metric == "tag_overlap":
                score = calculate_tag_similarity(problem.tags, example.problem.tags)
                matching_tags = list(
                    set(tag.lower() for tag in problem.tags)
                    & set(tag.lower() for tag in example.problem.tags)
                )

                # Update similarity score and matching tags
                example_copy = SimilarProblem(
                    problem=example.problem,
                    solution_code=example.solution_code,
                    similarity_score=score,
                    matching_tags=matching_tags,
                )

                if score >= self.min_similarity_score:
                    similarities.append(example_copy)

        # Sort by similarity score (descending)
        similarities.sort(key=lambda x: x.similarity_score, reverse=True)

        # Return top-k
        top_k = similarities[:k]

        self.logger.info(
            "similar_problems_retrieved",
            requested=k,
            found=len(similarities),
            returned=len(top_k),
        )

        return top_k

    def build_few_shot_prompt(self, problem: Problem, examples: list[SimilarProblem]) -> str:
        """
        Build few-shot prompt with examples.

        Args:
            problem: Target problem
            examples: List of similar problems

        Returns:
            Prompt string with examples
        """
        if not examples:
            # Fallback to base prompt without examples
            return self.build_base_prompt(problem)

        # Start with system instruction
        prompt_parts = ["You are an expert algorithm problem solver.\n"]

        # Add examples
        for i, example in enumerate(examples, 1):
            prompt_parts.append(f"\nExample {i}:")
            prompt_parts.append(f"Problem: {example.problem.title}")
            prompt_parts.append(f"Description: {example.problem.description}")
            if example.matching_tags:
                prompt_parts.append(f"Tags: {', '.join(example.matching_tags)}")
            prompt_parts.append(f"Solution:\n```python\n{example.solution_code}\n```\n")

        # Add target problem
        prompt_parts.append("\nNow solve this problem:\n")
        prompt_parts.append(self.build_base_prompt(problem))

        return "\n".join(prompt_parts)

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute Few-Shot Learning strategy.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult
        """
        self.logger.info(
            "executing_few_shot_learning_strategy",
            problem_id=problem.problem_id,
        )

        started = time.perf_counter()

        # Step 1: Retrieve similar problems
        similar_problems = self.retrieve_similar(problem, k=self.num_examples)

        # Step 2: Build few-shot prompt
        prompt = self.build_few_shot_prompt(problem, similar_problems)

        # Step 3: Get LLM response
        llm_response = None
        llm_error = None
        budget_stop = None
        try:
            llm_response = self.generate(prompt)
        except BudgetExhausted as e:
            budget_stop = str(e)
            self.logger.warning("llm_generation_stopped_on_budget", stop_reason=budget_stop)
        except Exception as e:
            llm_error = str(e)
            self.logger.error("llm_generation_failed", error=llm_error)

        # Step 4: Extract code
        code = None
        if llm_response is not None:
            code = self.extract_code(llm_response.text, problem)

        # Step 5: Execute in sandbox
        sandbox_result = None
        sandbox_error = None
        success = False

        if code:
            try:
                self._before_execute(code)

                if problem.public_test_cases:
                    sandbox_result = self.sandbox.execute(code, problem, stage="public")
                    success = sandbox_result.all_passed
                elif problem.feedback_test_cases:
                    sandbox_result = self.sandbox.execute(code, problem, stage="feedback")
                    success = sandbox_result.all_passed
                else:
                    # Hidden-only problems
                    success = True

                if sandbox_result:
                    feedback = (
                        f"All passed: {sandbox_result.all_passed}, "
                        f"Status: {sandbox_result.status}"
                    )
                    if sandbox_result.error_message:
                        feedback += f", Error: {sandbox_result.error_message}"
                    self._after_feedback(feedback)
            except Exception as e:
                sandbox_error = str(e)
                self.logger.error("sandbox_execution_failed", error=sandbox_error)
                self._after_feedback(f"Sandbox error: {sandbox_error}")

        # Create iteration result
        iteration_result = self.create_iteration_result(
            iteration=1,
            llm_response=llm_response,
            code=code,
            sandbox_result=sandbox_result,
            prompt=prompt,
            llm_error=llm_error,
            sandbox_error=sandbox_error,
            elapsed_seconds=time.perf_counter() - started,
        )

        # Create execution result
        execution_result = self.create_execution_result(
            problem=problem,
            iterations=[iteration_result],
            final_result=sandbox_result,
            success=success,
            llm_responses=[llm_response] if llm_response is not None else [],
            execution_time_seconds=time.perf_counter() - started,
        )

        if budget_stop is not None:
            execution_result = self.mark_budget_exhausted(execution_result, budget_stop)

        self.logger.info(
            "few_shot_learning_strategy_completed",
            problem_id=problem.problem_id,
            success=success,
            examples_used=len(similar_problems),
        )

        return execution_result
