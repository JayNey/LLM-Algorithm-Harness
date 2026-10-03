"""
Model capability profiling module.

Provides dimension classification, scoring, and analysis for model capabilities
across different algorithm types.
"""

from typing import Any

from src.models import ExecutionResult, Problem

# Algorithm dimension constants
DIMENSION_ARRAY = "Array"
DIMENSION_GRAPH = "Graph"
DIMENSION_DYNAMIC_PROGRAMMING = "Dynamic Programming"
DIMENSION_GREEDY = "Greedy"
DIMENSION_MATH = "Math"
DIMENSION_STRING = "String"
DIMENSION_OTHER = "Other"

# All dimensions in display order
ALL_DIMENSIONS = [
    DIMENSION_ARRAY,
    DIMENSION_GRAPH,
    DIMENSION_DYNAMIC_PROGRAMMING,
    DIMENSION_GREEDY,
    DIMENSION_MATH,
    DIMENSION_STRING,
    DIMENSION_OTHER,
]

# Tag-to-dimension mapping
# Maps problem tags to algorithm dimensions
TAG_TO_DIMENSION = {
    # Array dimension
    "array": DIMENSION_ARRAY,
    "list": DIMENSION_ARRAY,
    "sorting": DIMENSION_ARRAY,
    "two-pointers": DIMENSION_ARRAY,
    "sliding-window": DIMENSION_ARRAY,
    "matrix": DIMENSION_ARRAY,
    # Graph dimension
    "graph": DIMENSION_GRAPH,
    "tree": DIMENSION_GRAPH,
    "bfs": DIMENSION_GRAPH,
    "dfs": DIMENSION_GRAPH,
    "shortest-path": DIMENSION_GRAPH,
    "topological-sort": DIMENSION_GRAPH,
    "union-find": DIMENSION_GRAPH,
    # Dynamic Programming dimension
    "dp": DIMENSION_DYNAMIC_PROGRAMMING,
    "dynamic-programming": DIMENSION_DYNAMIC_PROGRAMMING,
    "memoization": DIMENSION_DYNAMIC_PROGRAMMING,
    "recursion": DIMENSION_DYNAMIC_PROGRAMMING,
    # Greedy dimension
    "greedy": DIMENSION_GREEDY,
    "interval": DIMENSION_GREEDY,
    # Math dimension
    "math": DIMENSION_MATH,
    "number-theory": DIMENSION_MATH,
    "combinatorics": DIMENSION_MATH,
    "geometry": DIMENSION_MATH,
    "bit-manipulation": DIMENSION_MATH,
    # String dimension
    "string": DIMENSION_STRING,
    "string-matching": DIMENSION_STRING,
    "trie": DIMENSION_STRING,
    "suffix-array": DIMENSION_STRING,
}


def classify_problem(problem: Problem | dict[str, Any]) -> list[str]:
    """
    Classify a problem into algorithm dimensions based on its tags.

    Args:
        problem: Problem instance or dict with tags/algorithm_tags

    Returns:
        List of dimension names the problem belongs to.
        Returns empty list if no tags match any dimension.
    """
    dimensions = set()

    # Handle both dict and Problem instances
    if isinstance(problem, dict):
        tags = problem.get("tags", []) or problem.get("algorithm_tags", [])
    else:
        tags = problem.tags

    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in TAG_TO_DIMENSION:
            dimensions.add(TAG_TO_DIMENSION[tag_lower])

    return sorted(dimensions)


def calculate_dimension_scores(
    results: list[ExecutionResult] | list[dict[str, Any]], problems: list[Problem] | list[dict[str, Any]]
) -> dict[str, dict[str, float]]:
    """
    Calculate dimension-based success rates for each model.

    Args:
        results: List of execution results (ExecutionResult instances or dicts)
        problems: List of problems with tags (Problem instances or dicts)

    Returns:
        Nested dict: {model_name: {dimension: score_0_to_100}}
        Score is 0.0 if no problems exist for that dimension.
    """
    # Build problem_id -> problem mapping - handle both dicts and model instances
    problem_map: dict[str, Problem | dict[str, Any]] = {}
    for p in problems:
        if isinstance(p, dict):
            pid = p.get("problem_id")
            if pid is not None:
                problem_map[pid] = p
        else:
            problem_map[p.problem_id] = p

    # Collect results by model and dimension
    # Structure: {model: {dimension: {"total": int, "success": int}}}
    model_dimension_stats: dict[str, dict[str, dict[str, int]]] = {}

    for result in results:
        # Handle both dict and ExecutionResult instances
        if isinstance(result, dict):
            problem_id = result.get("problem_id")
            model_name = result.get("model", "unknown")
            status = result.get("status")
            is_success = status == "success"
        else:
            problem_id = result.problem_id
            model_name = result.strategy
            is_success = result.is_successful()

        if problem_id not in problem_map:
            continue

        problem = problem_map[problem_id]
        dimensions = classify_problem(problem)

        if model_name not in model_dimension_stats:
            model_dimension_stats[model_name] = {}

        # Update stats for each dimension this problem belongs to
        for dimension in dimensions:
            if dimension not in model_dimension_stats[model_name]:
                model_dimension_stats[model_name][dimension] = {"total": 0, "success": 0}

            model_dimension_stats[model_name][dimension]["total"] += 1
            if is_success:
                model_dimension_stats[model_name][dimension]["success"] += 1

    # Calculate success rates and convert to 0-100 scale
    model_scores: dict[str, dict[str, float]] = {}

    for model_name in model_dimension_stats:
        model_scores[model_name] = {}
        for dimension in ALL_DIMENSIONS:
            if dimension in model_dimension_stats[model_name]:
                stats = model_dimension_stats[model_name][dimension]
                success_rate = stats["success"] / stats["total"] if stats["total"] > 0 else 0.0
                model_scores[model_name][dimension] = success_rate * 100.0
            else:
                model_scores[model_name][dimension] = 0.0

    return model_scores


def format_dimension_scores_for_radar(
    model_scores: dict[str, dict[str, float]]
) -> dict[str, Any]:
    """
    Format dimension scores for radar chart consumption.

    Args:
        model_scores: Nested dict from calculate_dimension_scores

    Returns:
        Dict with dimension_names and model_scores arrays for radar chart.
        Format: {dimension_names: [...], model_scores: {model: [score1, score2, ...]}}
    """
    if not model_scores:
        return {"dimension_names": [], "model_scores": {}}

    # Extract dimension names (all models have same dimensions)
    dimension_names = ALL_DIMENSIONS

    # Convert to radar format: {model: [score1, score2, ...]}
    radar_scores = {}
    for model_name, dims in model_scores.items():
        radar_scores[model_name] = [dims.get(dim, 0.0) for dim in dimension_names]

    return {"dimension_names": dimension_names, "model_scores": radar_scores}


def get_dimension_problem_counts(problems: list[Problem]) -> dict[str, int]:
    """
    Count the number of problems in each dimension.

    Problems can belong to multiple dimensions, so the sum of counts
    may exceed the total number of problems.

    Args:
        problems: List of problems with tags

    Returns:
        Dict mapping dimension name to problem count
    """
    dimension_counts: dict[str, int] = {dim: 0 for dim in ALL_DIMENSIONS}

    for problem in problems:
        dimensions = classify_problem(problem)
        for dimension in dimensions:
            if dimension in dimension_counts:
                dimension_counts[dimension] += 1

    return dimension_counts


def normalize_score_to_100(success_rate: float) -> float:
    """
    Normalize a success rate (0.0-1.0) to 0-100 scale.

    Args:
        success_rate: Success rate as a fraction (0.0-1.0)

    Returns:
        Score normalized to 0-100 scale
    """
    return success_rate * 100.0


def generate_capability_analysis(dimension_scores: dict[str, float]) -> str:
    """
    Generate capability analysis text identifying strengths and weaknesses.

    Args:
        dimension_scores: Dict mapping dimension names to scores (0-100 scale)

    Returns:
        Markdown-formatted analysis text
    """
    if not dimension_scores:
        return "No capability data available."

    # Identify strengths (≥80) and weaknesses (<50)
    strengths = [dim for dim, score in dimension_scores.items() if score >= 80]
    weaknesses = [dim for dim, score in dimension_scores.items() if score < 50]

    # Build analysis text
    lines = ["## Capability Analysis\n"]

    # Dimension scores
    lines.append("### Dimension Scores\n")
    for dim, score in sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- **{dim}**: {score:.1f}/100")
    lines.append("")

    # Strengths
    if strengths:
        lines.append("### Strengths (≥80)")
        for dim in strengths:
            score = dimension_scores[dim]
            lines.append(f"- **{dim}**: {score:.1f}/100")
        lines.append("")

    # Weaknesses
    if weaknesses:
        lines.append("### Weaknesses (<50)")
        for dim in weaknesses:
            score = dimension_scores[dim]
            lines.append(f"- **{dim}**: {score:.1f}/100")
        lines.append("")

    # Summary
    lines.append("### Summary")
    if strengths and weaknesses:
        lines.append(
            f"Strong performance in {len(strengths)} dimension(s), "
            f"needs improvement in {len(weaknesses)} dimension(s)."
        )
    elif strengths:
        lines.append(f"Strong performance across {len(strengths)} dimension(s).")
    elif weaknesses:
        lines.append(f"Needs improvement in {len(weaknesses)} dimension(s).")
    else:
        lines.append("Moderate performance across all dimensions.")

    return "\n".join(lines)

