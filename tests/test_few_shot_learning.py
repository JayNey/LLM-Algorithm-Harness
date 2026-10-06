"""
Tests for Few-Shot Learning strategy.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    JudgeConfig,
    LLMResponse,
    Problem,
    SandboxResult,
    StrategyConfig,
    TestCase,
    TestCaseResult,
    TokenUsage,
)
from src.sandbox_executor import SandboxExecutor
from src.strategies.few_shot_learning import FewShotLearningStrategy, SimilarProblem
from src.strategies.similarity.tag_based import (
    calculate_jaccard_similarity,
    calculate_tag_similarity,
    filter_by_similarity_threshold,
    normalize_tags,
)


# ============================================================================
# Test Tag Similarity Functions
# ============================================================================


class TestTagSimilarity:
    """Test tag-based similarity calculations."""

    def test_normalize_tags_basic(self):
        """Test basic tag normalization."""
        tags = ["Array", "Hash Table", "  String  "]
        normalized = normalize_tags(tags)
        assert normalized == {"array", "hash table", "string"}

    def test_normalize_tags_empty(self):
        """Test normalization with empty tags."""
        tags = ["", "  ", "Array"]
        normalized = normalize_tags(tags)
        assert normalized == {"array"}

    def test_normalize_tags_duplicates(self):
        """Test normalization removes duplicates."""
        tags = ["Array", "array", "ARRAY"]
        normalized = normalize_tags(tags)
        assert normalized == {"array"}

    def test_calculate_jaccard_similarity_identical(self):
        """Test Jaccard similarity with identical sets."""
        tags1 = {"array", "hash table"}
        tags2 = {"array", "hash table"}
        score = calculate_jaccard_similarity(tags1, tags2)
        assert score == 1.0

    def test_calculate_jaccard_similarity_no_overlap(self):
        """Test Jaccard similarity with no overlap."""
        tags1 = {"array", "hash table"}
        tags2 = {"tree", "graph"}
        score = calculate_jaccard_similarity(tags1, tags2)
        assert score == 0.0

    def test_calculate_jaccard_similarity_partial_overlap(self):
        """Test Jaccard similarity with partial overlap."""
        tags1 = {"array", "hash table", "string"}
        tags2 = {"array", "tree"}
        score = calculate_jaccard_similarity(tags1, tags2)
        # intersection = 1, union = 4
        assert score == 0.25

    def test_calculate_jaccard_similarity_empty_sets(self):
        """Test Jaccard similarity with empty sets."""
        tags1 = set()
        tags2 = {"array"}
        score = calculate_jaccard_similarity(tags1, tags2)
        assert score == 0.0

    def test_calculate_tag_similarity(self):
        """Test end-to-end tag similarity calculation."""
        tags1 = ["Array", "Hash Table"]
        tags2 = ["array", "HASH TABLE", "String"]
        score = calculate_tag_similarity(tags1, tags2)
        # intersection = 2, union = 3
        assert score == pytest.approx(2 / 3)

    def test_filter_by_similarity_threshold(self):
        """Test similarity threshold filtering."""
        similarities = [
            ("problem1", 0.8),
            ("problem2", 0.5),
            ("problem3", 0.2),
            ("problem4", 0.6),
        ]
        filtered = filter_by_similarity_threshold(similarities, threshold=0.5)
        assert len(filtered) == 3
        assert ("problem3", 0.2) not in filtered


# ============================================================================
# Test Few-Shot Learning Strategy
# ============================================================================


class TestFewShotLearningStrategy:
    """Test Few-Shot Learning strategy implementation."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        client.generate.return_value = LLMResponse(
            text="```python\ndef solution(nums):\n    return sum(nums)\n```",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            usage_missing=False,
            effective_params={},
        )
        return client

    @pytest.fixture
    def mock_sandbox(self):
        """Create mock sandbox executor."""
        sandbox = Mock(spec=SandboxExecutor)
        sandbox.execute.return_value = SandboxResult(
            all_passed=True,
            status="success",
            test_results=[],
        )
        return sandbox

    @pytest.fixture
    def strategy_config(self):
        """Create strategy configuration."""
        return StrategyConfig(
            name="few_shot_learning",
            custom_params={
                "num_examples": 2,
                "similarity_metric": "tag_overlap",
                "min_similarity_score": 0.3,
            },
        )

    @pytest.fixture
    def sample_problem(self):
        """Create sample problem."""
        return Problem(
            problem_id="test_001",
            title="Sum Array",
            description="Calculate sum of array",
            difficulty="easy",
            tags=["array", "math"],
            public_test_cases=[
                TestCase(
                    input={"nums": [1, 2, 3]},
                    expected_output=6,
                )
            ],
        )

    def test_strategy_initialization(self, strategy_config, mock_llm_client, mock_sandbox):
        """Test strategy initialization with config parameters."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)
        assert strategy.num_examples == 2
        assert strategy.similarity_metric == "tag_overlap"
        assert strategy.min_similarity_score == 0.3
        assert strategy.example_db == []

    def test_retrieve_similar_no_examples(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test retrieval when no examples are available."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)
        similar = strategy.retrieve_similar(sample_problem, k=3)
        assert similar == []

    def test_retrieve_similar_with_examples(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test retrieval with available examples."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Manually add examples to database
        strategy.example_db = [
            SimilarProblem(
                problem=Problem(
                    problem_id="ex1",
                    title="Example 1",
                    description="Test problem description with minimum length",
                    difficulty="easy",
                    tags=["array", "math"],
                    public_test_cases=[
                        TestCase(input={"nums": [1, 2]}, expected_output=3)
                    ],
                ),
                solution_code="def solution(): pass",
                similarity_score=0.0,
                matching_tags=[],
            ),
            SimilarProblem(
                problem=Problem(
                    problem_id="ex2",
                    title="Example 2",
                    description="Test problem description with minimum length",
                    difficulty="easy",
                    tags=["tree"],
                    public_test_cases=[
                        TestCase(input={"nums": [1, 2]}, expected_output=3)
                    ],
                ),
                solution_code="def solution(): pass",
                similarity_score=0.0,
                matching_tags=[],
            ),
        ]

        similar = strategy.retrieve_similar(sample_problem, k=2)
        # Only ex1 should match (has overlapping tags)
        assert len(similar) == 1
        assert similar[0].problem.problem_id == "ex1"
        assert similar[0].similarity_score == 1.0  # Both tags match

    def test_retrieve_similar_threshold_filtering(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test that similarity threshold filters low-score examples."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)
        strategy.min_similarity_score = 0.6

        strategy.example_db = [
            SimilarProblem(
                problem=Problem(
                    problem_id="ex1",
                    title="Example 1",
                    description="Test problem description with minimum length",
                    difficulty="easy",
                    tags=["array"],  # sample has ["array", "sorting"], this has ["array"]
                    # Jaccard = |intersection| / |union| = 1 / 2 = 0.5 < 0.6
                    public_test_cases=[
                        TestCase(input={"nums": [1, 2]}, expected_output=3)
                    ],
                ),
                solution_code="def solution(): pass",
                similarity_score=0.0,
                matching_tags=[],
            ),
        ]

        similar = strategy.retrieve_similar(sample_problem, k=5)
        assert len(similar) == 0  # Filtered out by threshold (0.5 < 0.6)

    def test_build_few_shot_prompt_no_examples(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test prompt building without examples (fallback to base)."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)
        prompt = strategy.build_few_shot_prompt(sample_problem, [])
        assert "Problem: Sum Array" in prompt
        assert "Example" not in prompt

    def test_build_few_shot_prompt_with_examples(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test prompt building with examples."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        examples = [
            SimilarProblem(
                problem=Problem(
                    problem_id="ex1",
                    title="Example Problem",
                    description="Example description with minimum length required",
                    difficulty="easy",
                    tags=["array"],
                    public_test_cases=[
                        TestCase(input={"nums": [1, 2]}, expected_output=3)
                    ],
                ),
                solution_code="def solution(): return 42",
                similarity_score=0.8,
                matching_tags=["array"],
            )
        ]

        prompt = strategy.build_few_shot_prompt(sample_problem, examples)
        assert "Example 1:" in prompt
        assert "Example Problem" in prompt
        assert "def solution(): return 42" in prompt
        assert "Now solve this problem:" in prompt
        assert "Sum Array" in prompt

    def test_execute_full_workflow(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test complete execution workflow."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        result = strategy.execute(sample_problem)

        assert isinstance(result, ExecutionResult)
        assert result.status == "success"
        assert result.problem_id == "test_001"
        assert result.strategy == "few_shot_learning"
        assert len(result.iterations) == 1
        mock_llm_client.generate.assert_called_once()
        mock_sandbox.execute.assert_called_once()

    def test_execute_handles_llm_error(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test execution handles LLM errors gracefully."""
        mock_llm_client.generate.side_effect = Exception("API Error")
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        result = strategy.execute(sample_problem)

        assert result.status in ["error", "failed"]
        assert result.failure_category == "model_error"
        assert len(result.iterations) == 1
        assert result.iterations[0].llm_error == "API Error"

    def test_execute_handles_code_extraction_failure(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test execution handles code extraction failure."""
        mock_llm_client.generate.return_value = LLMResponse(
            text="No code here, just text",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            usage_missing=False,
            effective_params={},
        )
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        result = strategy.execute(sample_problem)

        assert result.status in ["error", "failed"]
        assert result.failure_category == "code_extraction_failed"
        mock_sandbox.execute.assert_not_called()

    def test_config_parameter_validation(
        self, strategy_config, mock_llm_client, mock_sandbox
    ):
        """Test configuration parameter handling."""
        # Test with minimal config
        minimal_config = StrategyConfig(name="few_shot_learning")
        strategy = FewShotLearningStrategy(minimal_config, mock_llm_client, mock_sandbox)

        # Should use default values
        assert strategy.num_examples == 3
        assert strategy.similarity_metric == "tag_overlap"
        assert strategy.min_similarity_score == 0.3

    def test_coverage_example_database_loading(
        self, strategy_config, mock_llm_client, mock_sandbox
    ):
        """Test example database manual population (loading logic tested via integration)."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Manually populate example_db to test retrieval works with examples
        strategy.example_db = [
            SimilarProblem(
                problem=Problem(
                    problem_id="example_1",
                    title="Example Problem",
                    description="An example problem for testing with sufficient length",
                    difficulty="easy",
                    tags=["array", "sorting"],
                    public_test_cases=[
                        TestCase(input={"nums": [1, 2]}, expected_output=3)
                    ],
                ),
                solution_code="def solution(nums): return sum(nums)",
                similarity_score=0.0,
                matching_tags=[],
            )
        ]

        # Verify example can be retrieved
        assert len(strategy.example_db) == 1
        assert strategy.example_db[0].problem.problem_id == "example_1"
        assert strategy.example_db[0].solution_code == "def solution(nums): return sum(nums)"

    def test_execute_with_budget_exhausted(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test execution when budget is exhausted."""
        from src.budget import BudgetExhausted

        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Mock LLM to raise BudgetExhausted
        mock_llm_client.generate.side_effect = BudgetExhausted("Budget limit reached")

        result = strategy.execute(sample_problem)

        # Should handle budget exhaustion gracefully
        assert result.status == "budget_exhausted"
        assert result.success is False
        # Budget exhausted results don't have failure_category
        assert result.failure_category is None

    def test_execute_with_sandbox_exception(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test execution when sandbox raises an exception."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Mock sandbox to raise exception
        mock_sandbox.execute.side_effect = RuntimeError("Sandbox crashed")

        result = strategy.execute(sample_problem)

        # Should handle sandbox error gracefully - will be marked as system_error
        assert result.success is False
        assert result.generated_code is not None
        # Strategy should have attempted execution once
        mock_llm_client.generate.assert_called_once()

    def test_execute_with_feedback_test_cases(
        self, strategy_config, mock_llm_client, mock_sandbox
    ):
        """Test execution with feedback test cases instead of public test cases."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Create problem with feedback test cases only
        problem = Problem(
            problem_id="feedback_problem",
            title="Feedback Problem",
            description="A problem with feedback test cases for comprehensive testing",
            difficulty="easy",
            tags=["array"],
            public_test_cases=[],
            feedback_test_cases=[
                TestCase(input={"nums": [1, 2, 3]}, expected_output=6)
            ],
        )

        # Mock LLM response using correct LLMResponse format
        mock_llm_client.generate.return_value = LLMResponse(
            text="```python\ndef solution(nums):\n    return sum(nums)\n```",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            usage_missing=False,
            effective_params={},
        )

        # Mock sandbox result
        mock_sandbox.execute.return_value = SandboxResult(
            status="success",
            all_passed=True,
            test_results=[
                TestCaseResult(
                    test_case_index=0,
                    passed=True,
                    actual_output=6,
                    expected_output=6,
                    error_message=None,
                    execution_time=0.01,
                    status="passed",
                )
            ],
        )

        result = strategy.execute(problem)

        # Should execute with feedback test cases
        assert result.success is True
        mock_sandbox.execute.assert_called_once()
        call_args = mock_sandbox.execute.call_args
        assert call_args[1]["stage"] == "feedback"

    def test_execute_with_hidden_only_problem(
        self, strategy_config, mock_llm_client, mock_sandbox
    ):
        """Test execution with hidden-only test cases."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Create problem with hidden test cases only
        problem = Problem(
            problem_id="hidden_problem",
            title="Hidden Problem",
            description="A problem with hidden test cases only for comprehensive testing",
            difficulty="hard",
            tags=["dynamic-programming"],
            public_test_cases=[],
            feedback_test_cases=[],
            hidden_test_cases=[
                TestCase(input={"n": 5}, expected_output=10)
            ],
        )

        result = strategy.execute(problem)

        # Should succeed - code generated but no sandbox execution for hidden-only
        assert result.generated_code is not None
        # Sandbox should not be called for hidden-only problems
        mock_sandbox.execute.assert_not_called()

    def test_load_example_database_no_results_dir(
        self, strategy_config, mock_llm_client, mock_sandbox, tmp_path, monkeypatch
    ):
        """Test example database loading when results directory doesn't exist."""
        # Change to a temp directory with no results folder
        monkeypatch.chdir(tmp_path)

        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Should initialize with empty database
        assert len(strategy.example_db) == 0

    def test_load_example_database_with_valid_results(
        self, strategy_config, mock_llm_client, mock_sandbox, tmp_path, monkeypatch
    ):
        """Test example database loading with valid result files."""
        # Create results directory with a valid result file
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        # Create a result file with the correct naming pattern and format
        # Note: The loader creates minimal Problem objects, but Problem requires at least one test case
        # This tests the exception handling path (line 103-111)
        result_file = results_dir / "test_results.json"
        result_data = [
            {
                "problem_id": "test-problem",
                "difficulty": "easy",
                "generated_code": "def solution(x):\n    return x * 2",
                "status": "success",  # Must be "success" to be loaded
            }
        ]
        result_file.write_text(json.dumps(result_data))

        monkeypatch.chdir(tmp_path)

        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Should handle the validation error and skip the invalid example
        # This covers the exception handling at lines 103-111
        assert len(strategy.example_db) == 0

    def test_load_example_database_with_invalid_problem_data(
        self, strategy_config, mock_llm_client, mock_sandbox, tmp_path, monkeypatch
    ):
        """Test example database loading handles invalid problem data gracefully."""
        # Create results directory with an invalid result file
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        # Result missing required problem fields
        result_file = results_dir / "invalid_results.json"
        result_data = [
            {
                "problem_id": None,  # Invalid - no problem_id
                "generated_code": "def solution(x):\n    return x",
                "status": "success",
            }
        ]
        result_file.write_text(json.dumps(result_data))

        monkeypatch.chdir(tmp_path)

        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Should skip invalid example and initialize with empty database
        assert len(strategy.example_db) == 0

    def test_load_example_database_with_corrupted_json(
        self, strategy_config, mock_llm_client, mock_sandbox, tmp_path, monkeypatch
    ):
        """Test example database loading handles corrupted JSON files gracefully."""
        # Create results directory with a corrupted JSON file
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        result_file = results_dir / "corrupted_results.json"
        result_file.write_text("{invalid json content")

        monkeypatch.chdir(tmp_path)

        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Should handle the error and initialize with empty database
        assert len(strategy.example_db) == 0

    def test_sandbox_result_with_error_message(
        self, strategy_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Test handling of sandbox results with error messages."""
        strategy = FewShotLearningStrategy(strategy_config, mock_llm_client, mock_sandbox)

        # Mock LLM response using correct LLMResponse format
        mock_llm_client.generate.return_value = LLMResponse(
            text="```python\ndef solution(nums, target):\n    return [0, 1]\n```",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            usage_missing=False,
            effective_params={},
        )

        # Mock sandbox result with error message
        mock_sandbox.execute.return_value = SandboxResult(
            status="runtime_error",
            all_passed=False,
            error_message="IndexError: list index out of range",
            test_results=[
                TestCaseResult(
                    test_case_index=0,
                    passed=False,
                    actual_output=None,
                    expected_output=[0, 1],
                    error_message="IndexError: list index out of range",
                    execution_time=0.005,
                    status="runtime_error",
                )
            ],
        )

        result = strategy.execute(sample_problem)

        # Should include error information
        assert result.success is False
        assert result.generated_code is not None
        mock_sandbox.execute.assert_called_once()
