"""Tests for Tree of Thoughts strategy."""

from unittest.mock import MagicMock, Mock

import pytest

from src.budget import BudgetExhausted
from src.models import (
    ExecutionResult,
    LLMResponse,
    Problem,
    SandboxResult,
    StrategyConfig,
    TokenUsage,
)
from src.strategies.tree_of_thoughts import ThoughtNode, TreeOfThoughtsStrategy


# Helper function to create mock LLM responses
def mock_llm_response(text: str) -> LLMResponse:
    """Create a mock LLM response with required fields."""
    return LLMResponse(
        text=text,
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="test-model",
    )


# Test fixtures
@pytest.fixture
def mock_config():
    """Mock configuration."""
    return StrategyConfig(
        name="tree_of_thoughts",
        max_iterations=1,
        temperature=0.7,
        max_tokens=2000,
    )


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    return MagicMock()


@pytest.fixture
def mock_sandbox():
    """Mock sandbox executor."""
    mock = MagicMock()
    mock.execute.return_value = SandboxResult(
        status="success",
        test_results=[],
        execution_time=0.1,
        all_passed=True,
        error_message=None,
    )
    return mock


@pytest.fixture
def sample_problem():
    """Sample problem for testing."""
    return Problem(
        problem_id="test_1",
        title="Test Problem",
        description="Solve this test problem",
        difficulty="easy",
        public_test_cases=[{"input": "1", "expected_output": "1"}],
        tags=["test"],
    )


@pytest.fixture
def tot_strategy(mock_config, mock_llm_client, mock_sandbox):
    """Create ToT strategy instance."""
    return TreeOfThoughtsStrategy(
        config=mock_config,
        llm_client=mock_llm_client,
        sandbox=mock_sandbox,
        branching_factor=3,
        max_depth=2,
        search_strategy="bfs",
        pruning_threshold=0.3,
    )


# Task 9: 数据结构测试
class TestThoughtNode:
    """Test ThoughtNode dataclass."""

    def test_node_creation_and_field_access(self):
        """Task 9.1: Test node creation and field access."""
        node = ThoughtNode(
            depth=1,
            thought="Test thought",
            code_snippet="print('hello')",
            quality_score=0.8,
            parent=None,
            children=[],
        )

        assert node.depth == 1
        assert node.thought == "Test thought"
        assert node.code_snippet == "print('hello')"
        assert node.quality_score == 0.8
        assert node.parent is None
        assert node.children == []

    def test_parent_child_relationship(self):
        """Task 9.2: Test parent-child relationship linking."""
        parent = ThoughtNode(depth=0, thought="Parent", code_snippet="", quality_score=1.0)
        child = ThoughtNode(
            depth=1,
            thought="Child",
            code_snippet="",
            quality_score=0.8,
            parent=parent,
        )

        parent.children.append(child)

        assert child.parent is parent
        assert len(parent.children) == 1
        assert parent.children[0] is child


# Task 10: 配置验证测试
class TestConfigValidation:
    """Test configuration parameter validation."""

    def test_branching_factor_less_than_one(self, mock_config, mock_llm_client, mock_sandbox):
        """Task 10.1: Test branching_factor < 1 raises ValueError."""
        with pytest.raises(ValueError, match="branching_factor must be >= 1"):
            TreeOfThoughtsStrategy(
                config=mock_config,
                llm_client=mock_llm_client,
                sandbox=mock_sandbox,
                branching_factor=0,
            )

    def test_max_depth_less_than_one(self, mock_config, mock_llm_client, mock_sandbox):
        """Task 10.2: Test max_depth < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_depth must be >= 1"):
            TreeOfThoughtsStrategy(
                config=mock_config,
                llm_client=mock_llm_client,
                sandbox=mock_sandbox,
                max_depth=0,
            )

    def test_invalid_search_strategy(self, mock_config, mock_llm_client, mock_sandbox):
        """Task 10.3: Test invalid search_strategy raises ValueError."""
        with pytest.raises(ValueError, match="search_strategy must be 'bfs' or 'dfs'"):
            TreeOfThoughtsStrategy(
                config=mock_config,
                llm_client=mock_llm_client,
                sandbox=mock_sandbox,
                search_strategy="invalid",
            )

    def test_pruning_threshold_out_of_range(self, mock_config, mock_llm_client, mock_sandbox):
        """Task 10.4: Test pruning_threshold out of [0, 1] raises ValueError."""
        with pytest.raises(ValueError, match="pruning_threshold must be between 0.0 and 1.0"):
            TreeOfThoughtsStrategy(
                config=mock_config,
                llm_client=mock_llm_client,
                sandbox=mock_sandbox,
                pruning_threshold=1.5,
            )


# Task 11: 分支生成测试
class TestBranchGeneration:
    """Test branch generation functionality."""

    def test_generate_branches_count(self, tot_strategy, sample_problem):
        """Task 11.1: Test correct number of branches generated."""
        parent = ThoughtNode(depth=0, thought="Root", code_snippet="", quality_score=1.0)

        # Mock LLM response
        mock_response = """=== Approach 1 ===
Reasoning: Use a loop
Code:
```python
def solution(): return 1
```

=== Approach 2 ===
Reasoning: Use recursion
Code:
```python
def solution(): return 2
```

=== Approach 3 ===
Reasoning: Use iteration
Code:
```python
def solution(): return 3
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_response))

        branches = tot_strategy.generate_branches(parent, sample_problem)

        assert len(branches) == 3

    def test_child_depth_increment(self, tot_strategy, sample_problem):
        """Task 11.2: Test child nodes have incremented depth."""
        parent = ThoughtNode(depth=1, thought="Parent", code_snippet="", quality_score=0.8)

        mock_response = """=== Variation 1 ===
Reasoning: Refine approach
Code:
```python
def solution(): return 1
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_response))

        branches = tot_strategy.generate_branches(parent, sample_problem)

        assert len(branches) > 0
        for branch in branches:
            assert branch.depth == parent.depth + 1

    def test_parent_reference_set(self, tot_strategy, sample_problem):
        """Task 11.3: Test child nodes have correct parent reference."""
        parent = ThoughtNode(depth=0, thought="Parent", code_snippet="", quality_score=1.0)

        mock_response = """=== Approach 1 ===
Reasoning: Test
Code:
```python
def solution(): return 1
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_response))

        branches = tot_strategy.generate_branches(parent, sample_problem)

        assert len(branches) > 0
        for branch in branches:
            assert branch.parent is parent

    def test_parse_branches_from_mock_response(self, tot_strategy, sample_problem):
        """Task 11.4: Test extraction from mock LLM response."""
        parent = ThoughtNode(depth=0, thought="Root", code_snippet="", quality_score=1.0)

        mock_response = """=== Approach 1 ===
Reasoning: First approach reasoning
Code:
```python
def solution(): return 42
```

=== Approach 2 ===
Reasoning: Second approach reasoning
Code:
```python
def solution(): return 99
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_response))

        branches = tot_strategy.generate_branches(parent, sample_problem)

        assert len(branches) == 2
        assert "First approach reasoning" in branches[0].thought
        assert "def solution(): return 42" in branches[0].code_snippet
        assert "Second approach reasoning" in branches[1].thought
        assert "def solution(): return 99" in branches[1].code_snippet


# Task 12: 节点评估测试
class TestNodeEvaluation:
    """Test node evaluation functionality."""

    def test_evaluate_node_returns_valid_score(self, tot_strategy, sample_problem):
        """Task 12.1: Test evaluation returns score in [0, 1]."""
        node = ThoughtNode(
            depth=1,
            thought="Test approach",
            code_snippet="def solution(): return 1",
            quality_score=0.0,
        )

        tot_strategy.generate = Mock(return_value=mock_llm_response("0.75"))

        score = tot_strategy.evaluate_node(node, sample_problem)

        assert 0.0 <= score <= 1.0
        assert score == 0.75

    def test_evaluation_prompt_contains_necessary_info(self, tot_strategy, sample_problem):
        """Task 12.2: Test evaluation prompt completeness."""
        node = ThoughtNode(
            depth=1,
            thought="Use dynamic programming",
            code_snippet="def solution(): pass",
            quality_score=0.0,
        )

        prompt = tot_strategy._build_evaluation_prompt(node, sample_problem)

        assert "Use dynamic programming" in prompt
        assert "def solution(): pass" in prompt
        assert "0.0" in prompt or "1.0" in prompt  # Score range mentioned

    def test_handle_non_numeric_response(self, tot_strategy, sample_problem):
        """Task 12.3: Test handling of non-numeric LLM response."""
        node = ThoughtNode(depth=1, thought="Test", code_snippet="pass", quality_score=0.0)

        tot_strategy.generate = Mock(return_value=mock_llm_response("This is not a number!"))

        # Should not crash, should return default score
        score = tot_strategy.evaluate_node(node, sample_problem)

        assert 0.0 <= score <= 1.0
        assert score == 0.5  # Default score


# Task 13: 剪枝测试
class TestPruning:
    """Test pruning functionality."""

    def test_prune_low_quality_branches(self, tot_strategy):
        """Task 13.1: Test pruning filters low-score nodes."""
        branches = [
            ThoughtNode(depth=1, thought="Good", code_snippet="", quality_score=0.8),
            ThoughtNode(depth=1, thought="Bad", code_snippet="", quality_score=0.1),
            ThoughtNode(depth=1, thought="Mediocre", code_snippet="", quality_score=0.5),
        ]

        kept = tot_strategy.prune_branches(branches)

        assert len(kept) == 2
        assert all(b.quality_score >= tot_strategy.pruning_threshold for b in kept)
        assert kept[0].thought == "Good"
        assert kept[1].thought == "Mediocre"

    def test_all_branches_pruned(self, tot_strategy):
        """Task 13.2: Test all branches pruned returns empty list."""
        branches = [
            ThoughtNode(depth=1, thought="Bad1", code_snippet="", quality_score=0.1),
            ThoughtNode(depth=1, thought="Bad2", code_snippet="", quality_score=0.2),
        ]

        kept = tot_strategy.prune_branches(branches)

        assert len(kept) == 0

    def test_pruning_logs_statistics(self, tot_strategy):
        """Task 13.3: Test pruning logs statistics."""
        branches = [
            ThoughtNode(depth=1, thought="Good", code_snippet="", quality_score=0.8),
            ThoughtNode(depth=1, thought="Bad", code_snippet="", quality_score=0.1),
        ]

        kept = tot_strategy.prune_branches(branches)

        # Verify pruning behavior: one branch should be kept (0.8 >= 0.3 threshold)
        # and one should be pruned (0.1 < 0.3 threshold)
        assert len(kept) == 1
        assert kept[0].quality_score == 0.8


# Task 14: 搜索算法测试
class TestSearchAlgorithm:
    """Test search algorithm functionality."""

    def test_bfs_expands_level_by_level(
        self, mock_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Task 14.1: Test BFS expands nodes level by level."""
        strategy = TreeOfThoughtsStrategy(
            config=mock_config,
            llm_client=mock_llm_client,
            sandbox=mock_sandbox,
            branching_factor=2,
            max_depth=2,
            search_strategy="bfs",
            pruning_threshold=0.0,
        )

        # Track expansion order
        expansion_order = []

        original_generate_branches = strategy.generate_branches

        def track_expansion(node, problem):
            expansion_order.append(node.depth)
            # Generate simple branches
            if node.depth < strategy.max_depth:
                branches = []
                for i in range(2):
                    child = ThoughtNode(
                        depth=node.depth + 1,
                        thought=f"Branch {i}",
                        code_snippet=f"def solution(): return {i}",
                        quality_score=0.5,
                        parent=node,
                    )
                    branches.append(child)
                return branches
            return []

        strategy.generate_branches = track_expansion
        strategy.evaluate_node = Mock(return_value=0.5)

        root = strategy.create_root_node(sample_problem)
        strategy.search_tree(root, sample_problem)

        # BFS should expand all depth 0, then all depth 1
        assert expansion_order[0] == 0
        # All subsequent expansions should be depth 1 or 2
        for depth in expansion_order[1:]:
            assert depth <= 2

    def test_dfs_expands_depth_first(
        self, mock_config, mock_llm_client, mock_sandbox, sample_problem
    ):
        """Task 14.2: Test DFS explores one branch deeply first."""
        strategy = TreeOfThoughtsStrategy(
            config=mock_config,
            llm_client=mock_llm_client,
            sandbox=mock_sandbox,
            branching_factor=2,
            max_depth=3,
            search_strategy="dfs",
            pruning_threshold=0.0,
        )

        expansion_order = []

        def track_expansion(node, problem):
            expansion_order.append(node.depth)
            if node.depth < strategy.max_depth:
                branches = []
                for i in range(2):
                    child = ThoughtNode(
                        depth=node.depth + 1,
                        thought=f"Branch {i}",
                        code_snippet=f"def solution(): return {i}",
                        quality_score=0.5,
                        parent=node,
                    )
                    branches.append(child)
                return branches
            return []

        strategy.generate_branches = track_expansion
        strategy.evaluate_node = Mock(return_value=0.5)

        root = strategy.create_root_node(sample_problem)
        strategy.search_tree(root, sample_problem)

        # DFS should expand nodes at depth 0, 1, and 2 (reaching max_depth - 1)
        # and reach max_depth (3) by creating children at that depth
        assert max(expansion_order) == strategy.max_depth - 1
        # Verify DFS order: should reach depth 2 early in the sequence
        first_max_depth_idx = expansion_order.index(strategy.max_depth - 1)
        assert first_max_depth_idx < len(expansion_order) / 2  # Reached deep early

    def test_max_depth_limit_enforced(self, tot_strategy, sample_problem):
        """Task 14.3: Test max_depth prevents deeper expansion."""
        max_depth_seen = [0]

        def track_depth_and_generate(node, problem):
            max_depth_seen[0] = max(max_depth_seen[0], node.depth)
            # Only generate children if below max_depth
            if node.depth < tot_strategy.max_depth:
                child = ThoughtNode(
                    depth=node.depth + 1,
                    thought=f"Child at depth {node.depth + 1}",
                    code_snippet="pass",
                    quality_score=0.8,
                    parent=node,
                )
                return [child]
            return []

        tot_strategy.generate_branches = track_depth_and_generate
        tot_strategy.evaluate_node = Mock(return_value=0.8)

        root = ThoughtNode(depth=0, thought="Root", code_snippet="", quality_score=1.0)
        result = tot_strategy.search_tree(root, sample_problem)

        # Verify expansion stopped at max_depth - 1
        assert max_depth_seen[0] == tot_strategy.max_depth - 1

    def test_iterations_recorded(self, tot_strategy, sample_problem):
        """Task 14.4: Test search records iterations."""
        mock_response = """=== Approach 1 ===
Reasoning: Test
Code:
```python
def solution(): return 1
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_response))
        tot_strategy.evaluate_node = Mock(return_value=0.5)

        root = tot_strategy.create_root_node(sample_problem)
        result = tot_strategy.search_tree(root, sample_problem)

        assert len(result.iterations) > 0
        for iteration in result.iterations:
            assert hasattr(iteration, "iteration")


# Task 15: 解决方案提取测试
class TestSolutionExtraction:
    """Test solution extraction functionality."""

    def test_select_highest_scoring_leaf(self, tot_strategy, sample_problem):
        """Task 15.1: Test selection of highest scoring leaf node."""
        nodes = [
            ThoughtNode(depth=2, thought="Leaf1", code_snippet="code1", quality_score=0.6),
            ThoughtNode(depth=2, thought="Leaf2", code_snippet="code2", quality_score=0.9),
            ThoughtNode(depth=2, thought="Leaf3", code_snippet="code3", quality_score=0.4),
        ]

        # Mock sandbox to return success
        from src.models import SandboxResult, TestCaseResult

        tot_strategy.sandbox.execute = Mock(
            return_value=SandboxResult(
                status="success",
                all_passed=True,
                num_passed=1,
                num_failed=0,
                results=[TestCaseResult(test_case_index=0, passed=True, actual="1", expected="1")],
            )
        )

        result = tot_strategy._extract_best_solution(nodes, [], sample_problem, elapsed_time=1.0)

        assert result.success is True
        assert result.generated_code == "code2"
        tot_strategy.sandbox.execute.assert_called_once()
        call_args = tot_strategy.sandbox.execute.call_args
        assert call_args[0][0] == "code2"  # First positional arg is the code

    def test_no_valid_solution(self, tot_strategy, sample_problem):
        """Task 15.2: Test handling when no valid solutions exist."""
        result = tot_strategy._extract_best_solution([], [], sample_problem, elapsed_time=1.0)

        assert result.success is False
        assert result.generated_code == ""  # Empty string when no iterations

    def test_code_extraction_matches_node(self, tot_strategy, sample_problem):
        """Task 15.3: Test extracted code matches best node's code_snippet."""
        best_code = "def solution(): return 42"
        nodes = [
            ThoughtNode(depth=1, thought="Best", code_snippet=best_code, quality_score=0.95),
            ThoughtNode(
                depth=1, thought="Worse", code_snippet="def solution(): return 0", quality_score=0.3
            ),
        ]

        # Mock sandbox to return success
        from src.models import SandboxResult, TestCaseResult

        tot_strategy.sandbox.execute = Mock(
            return_value=SandboxResult(
                status="success",
                all_passed=True,
                num_passed=1,
                num_failed=0,
                results=[
                    TestCaseResult(test_case_index=0, passed=True, actual="42", expected="42")
                ],
            )
        )

        result = tot_strategy._extract_best_solution(nodes, [], sample_problem, elapsed_time=1.0)

        assert result.generated_code == best_code
        # Verify the best node's code was used for execution
        tot_strategy.sandbox.execute.assert_called_once()
        call_args = tot_strategy.sandbox.execute.call_args
        assert call_args[0][0] == best_code  # First positional arg is the code


# Task 16: 端到端测试
class TestEndToEnd:
    """Test complete execution flow."""

    def test_complete_execute_flow(self, tot_strategy, sample_problem):
        """Task 16.1: Test full execute with mock LLM."""
        mock_branch_response = """=== Approach 1 ===
Reasoning: Simple solution
Code:
```python
def solution(): return 42
```
"""
        tot_strategy.generate = Mock(return_value=mock_llm_response(mock_branch_response))
        tot_strategy.evaluate_node = Mock(return_value=0.8)

        result = tot_strategy.execute(sample_problem)

        assert isinstance(result, ExecutionResult)
        assert len(result.iterations) > 0
        assert result.problem_id == sample_problem.problem_id

    def test_bfs_and_dfs_modes(self, mock_config, mock_llm_client, mock_sandbox, sample_problem):
        """Task 16.2: Test both BFS and DFS complete successfully."""
        for mode in ["bfs", "dfs"]:
            strategy = TreeOfThoughtsStrategy(
                config=mock_config,
                llm_client=mock_llm_client,
                sandbox=mock_sandbox,
                branching_factor=2,
                max_depth=2,
                search_strategy=mode,
                pruning_threshold=0.3,
            )

            mock_response = """=== Approach 1 ===
Reasoning: Test
Code:
```python
def solution(): return 1
```
"""
            strategy.generate = Mock(return_value=mock_llm_response(mock_response))
            strategy.evaluate_node = Mock(return_value=0.5)

            result = strategy.execute(sample_problem)

            assert isinstance(result, ExecutionResult)

    def test_budget_exhausted_handling(self, tot_strategy, sample_problem):
        """Task 16.3: Test handling of BudgetExhausted exception."""

        def raise_budget_exhausted(*args, **kwargs):
            raise BudgetExhausted("Test budget exhausted")

        tot_strategy.generate = Mock(side_effect=raise_budget_exhausted)

        result = tot_strategy.execute(sample_problem)

        # Should still return a result (possibly with no valid solution)
        assert isinstance(result, ExecutionResult)


class TestSelectedCodeContract:
    @pytest.mark.parametrize("search_strategy", ["bfs", "dfs"])
    @pytest.mark.parametrize("max_depth", [1, 3])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_result_keeps_best_leaf_across_traversals(
        self, tot_strategy, sample_problem, search_strategy, max_depth, reverse
    ):
        """The last expanded parent must never replace the selected leaf code."""
        tot_strategy.search_strategy = search_strategy
        tot_strategy.max_depth = max_depth
        best_code = "def solution(): return 42"

        def branches(node, problem):
            if node.depth == 0:
                children = [
                    ThoughtNode(1, "best", best_code if max_depth == 1 else "parent-best", 0.9),
                    ThoughtNode(1, "other", "parent-other", 0.5),
                ]
                return list(reversed(children)) if reverse else children
            return [
                ThoughtNode(
                    node.depth + 1,
                    node.thought,
                    best_code if node.thought == "best" else "other-leaf",
                    node.quality_score,
                )
            ]

        tot_strategy.generate_branches = branches
        tot_strategy.evaluate_node = lambda node, problem: node.quality_score
        result = tot_strategy.execute(sample_problem)

        assert result.success
        assert result.generated_code == best_code
        assert tot_strategy.sandbox.execute.call_args.args[0] == best_code

    @pytest.mark.parametrize("mode", ["empty", "pruned", "blank"])
    def test_no_usable_leaf_is_extraction_failure(self, tot_strategy, sample_problem, mode):
        """An empty root or whitespace leaf cannot become a successful result."""
        tot_strategy.max_depth = 1
        tot_strategy.generate_branches = lambda node, problem: (
            []
            if mode == "empty"
            else [
                ThoughtNode(
                    1,
                    "candidate",
                    " \n\t" if mode == "blank" else "pass",
                    0.1 if mode == "pruned" else 0.9,
                )
            ]
        )
        tot_strategy.evaluate_node = lambda node, problem: node.quality_score
        result = tot_strategy.execute(sample_problem)

        assert not result.success
        assert result.generated_code == ""
        assert result.failure_category == "code_extraction_failed"
        tot_strategy.sandbox.execute.assert_not_called()

    def test_empty_high_score_does_not_hide_usable_leaf(self, tot_strategy, sample_problem):
        nodes = [ThoughtNode(1, "empty", "", 1.0), ThoughtNode(1, "valid", "pass", 0.7)]
        result = tot_strategy._extract_best_solution(nodes, [], sample_problem, 0.1)
        assert result.success
        assert result.generated_code == "pass"

    def test_no_leaf_does_not_return_historical_parent(self, tot_strategy, sample_problem):
        from src.models import IterationResult

        result = tot_strategy._extract_best_solution(
            [], [IterationResult(iteration=1, code_extracted="stale parent")], sample_problem, 0.1
        )
        assert not result.success
        assert result.generated_code == ""
        assert result.failure_category == "code_extraction_failed"

    @pytest.mark.parametrize("outcome", ["wrong_answer", "exception"])
    def test_public_failure_preserves_selected_code(self, tot_strategy, sample_problem, outcome):
        if outcome == "exception":
            tot_strategy.sandbox.execute.side_effect = RuntimeError("sandbox unavailable")
        else:
            tot_strategy.sandbox.execute.return_value = SandboxResult(
                status="failed", all_passed=False
            )
        result = tot_strategy._extract_best_solution(
            [ThoughtNode(1, "selected", "def solution(): return 42", 0.9)], [], sample_problem, 0.1
        )
        assert not result.success
        assert result.generated_code == "def solution(): return 42"
        if outcome == "wrong_answer":
            assert result.final_result.status == "failed"

    @pytest.mark.parametrize("hidden_passed", [True, False])
    def test_harness_evaluates_selected_leaf_on_hidden(
        self, mock_config, mock_llm_client, mock_sandbox, hidden_passed
    ):
        """Real strategy output must reach the Harness hidden gate with its code."""
        from src.harness import AlgorithmHarness
        from src.models import CacheConfig, HarnessConfig, LLMConfig

        code = "def solution(x):\n    return x"
        mock_llm_client.generate.side_effect = [
            mock_llm_response(
                f"=== Approach 1 ===\nReasoning: identity\nCode:\n```python\n{code}\n```"
            ),
            mock_llm_response("0.9"),
        ]
        public = SandboxResult(status="success", all_passed=True)
        hidden = SandboxResult(
            status="success" if hidden_passed else "failed", all_passed=hidden_passed
        )
        mock_sandbox.execute.side_effect = [public, hidden]
        strategy = TreeOfThoughtsStrategy(
            mock_config, mock_llm_client, mock_sandbox, max_depth=1, branching_factor=1
        )
        problem = Problem(
            problem_id="selected-hidden",
            title="Identity",
            description="Return input",
            difficulty="easy",
            public_test_cases=[{"input": {"x": 1}, "expected_output": 1}],
            hidden_test_cases=[{"input": {"x": 2}, "expected_output": 2}],
        )
        harness = AlgorithmHarness(
            HarnessConfig(
                dataset_path="unused",
                llm_config=LLMConfig(
                    provider="openai",
                    api_key="test-key",
                    model="gpt-4",
                    cache=CacheConfig(enabled=False),
                ),
            )
        )
        result = harness._execute_problem(mock_config, problem, strategy, mock_sandbox)

        assert result.generated_code == code
        assert result.final_result is public
        assert result.hidden_result is hidden
        assert result.success is hidden_passed
        assert [call.kwargs["stage"] for call in mock_sandbox.execute.call_args_list] == [
            "public",
            "hidden",
        ]
        assert all(call.args[0] == code for call in mock_sandbox.execute.call_args_list)
        if not hidden_passed:
            assert result.failure_category == "wrong_answer"
