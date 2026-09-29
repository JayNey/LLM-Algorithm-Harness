"""Tests for canonical tag normalization and deterministic recommendations."""

import json

import yaml

from src.utils.tag_manager import TagManager


def test_normalize_multilingual_aliases_and_deduplicate():
    manager = TagManager()

    assert manager.normalize_tags(["hash_map", "哈希表", "hash-table", "ARRAY", "数组"]) == [
        "hash-table",
        "array",
    ]


def test_custom_mapping_overrides_and_extends_defaults(tmp_path):
    mapping_path = tmp_path / "tags.yaml"
    mapping_path.write_text(
        yaml.safe_dump(
            {
                "tags": {
                    "segment-tree": {
                        "aliases": ["segment_tree", "线段树"],
                        "keywords": ["segment tree", "线段树"],
                    }
                },
                "aliases": {"range-tree": "segment-tree"},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    manager = TagManager(mapping_path)

    assert manager.normalize_tag("segment_tree") == "segment-tree"
    assert manager.normalize_tag("range-tree") == "segment-tree"
    assert manager.normalize_tag("hash_map") == "hash-table"
    assert manager.recommend_tags("Segment tree range query", "Use a segment tree.") == [
        {
            "tag": "segment-tree",
            "confidence": 0.88,
            "matched_keywords": ["segment tree"],
            "reason": "title/description keyword match",
        }
    ]


def test_keyword_recommendation_matches_labeled_examples_above_80_percent():
    manager = TagManager()
    samples = [
        ("Binary search", "Find the lower bound in a sorted array.", "binary-search"),
        ("Sliding window", "Use a sliding window over the string.", "sliding-window"),
        ("Dynamic programming", "Solve with dp over the sequence.", "dynamic-programming"),
        ("Two pointers", "Apply two pointer traversal.", "two-pointers"),
        ("Union find", "Merge components with disjoint set union.", "union-find"),
    ]
    correct = 0
    for title, description, expected in samples:
        suggestions = manager.recommend_tags(title, description)
        if suggestions and suggestions[0]["tag"] == expected:
            correct += 1

    assert correct / len(samples) > 0.8


def test_normalize_dataset_is_preview_by_default_and_writes_explicit_output(tmp_path):
    source = tmp_path / "problems.json"
    source.write_text(
        json.dumps(
            [
                {
                    "problem_id": "p1",
                    "title": "Hash map lookup",
                    "description": "Use a hash map to find a pair in an array.",
                    "tags": ["hash_map"],
                }
            ]
        ),
        encoding="utf-8",
    )
    manager = TagManager()

    preview = manager.normalize_dataset(source)
    assert preview["normalized_dataset"] is None
    assert preview["problems"][0]["normalized_tags"] == ["hash-table"]
    assert preview["problems"][0]["suggestions"]
    assert preview["tag_counts_after"] == {"hash-table": 1}
    assert json.loads(source.read_text(encoding="utf-8"))[0]["tags"] == ["hash_map"]

    output = tmp_path / "normalized.json"
    report = manager.normalize_dataset(source, output, apply_recommendations=True)
    normalized = json.loads(output.read_text(encoding="utf-8"))
    assert report["applied_suggestion_count"] >= 1
    assert normalized[0]["tags"] == ["hash-table", "array"]
