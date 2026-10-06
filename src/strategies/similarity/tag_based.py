"""
Tag-based similarity calculation for Few-Shot Learning.
"""

from typing import List, Set


def normalize_tags(tags: List[str]) -> Set[str]:
    """
    Normalize and deduplicate tags.

    Args:
        tags: List of tags

    Returns:
        Set of normalized tags (lowercase, stripped)
    """
    return {tag.lower().strip() for tag in tags if tag.strip()}


def calculate_jaccard_similarity(tags1: Set[str], tags2: Set[str]) -> float:
    """
    Calculate Jaccard similarity between two tag sets.

    Jaccard similarity = |intersection| / |union|

    Args:
        tags1: First tag set
        tags2: Second tag set

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not tags1 or not tags2:
        return 0.0

    intersection = tags1 & tags2
    union = tags1 | tags2

    if not union:
        return 0.0

    return len(intersection) / len(union)


def calculate_tag_similarity(tags1: List[str], tags2: List[str]) -> float:
    """
    Calculate similarity between two tag lists.

    Args:
        tags1: First tag list
        tags2: Second tag list

    Returns:
        Similarity score between 0.0 and 1.0
    """
    normalized_tags1 = normalize_tags(tags1)
    normalized_tags2 = normalize_tags(tags2)

    return calculate_jaccard_similarity(normalized_tags1, normalized_tags2)


def filter_by_similarity_threshold(
    similarities: List[tuple], threshold: float
) -> List[tuple]:
    """
    Filter similarity results by threshold.

    Args:
        similarities: List of (item, score) tuples
        threshold: Minimum similarity score

    Returns:
        Filtered list of (item, score) tuples where score >= threshold
    """
    return [(item, score) for item, score in similarities if score >= threshold]
