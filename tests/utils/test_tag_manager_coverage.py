"""Tests for tag normalization and recommendation (utils/tag_manager)."""

import json

import pytest

from src.utils.tag_manager import TagManager


@pytest.fixture
def manager():
    return TagManager()


class TestNormalizeTags:
    def test_normalizes_known_variants(self, manager):
        result = manager.normalize_tags(["DP", "dynamic programming", "Arrays"])
        assert all(isinstance(tag, str) for tag in result)

    def test_deduplicates_case_insensitively(self, manager):
        result = manager.normalize_tags(["dp", "DP", "DP"])
        lowered = [tag.lower() for tag in result]
        assert len(lowered) == len(set(lowered))

    def test_none_and_empty_inputs(self, manager):
        assert manager.normalize_tags(None) == []
        assert manager.normalize_tags([]) == []

    def test_non_string_tags_raise_type_error(self, manager):
        with pytest.raises(TypeError, match="Tags must be strings"):
            manager.normalize_tags(["dp", None, "graph"])


class TestRecommendTags:
    def test_title_match_suggests_canonical_tag(self, manager):
        suggestions = manager.recommend_tags(
            "Two Sum dynamic programming problem", "array based solution", min_confidence=0.0
        )
        names = {item["tag"] for item in suggestions}
        assert any("dp" in name or "dynamic" in name for name in names)

    def test_existing_tags_are_not_resuggested(self, manager):
        suggestions = manager.recommend_tags(
            "dynamic programming problem", "", existing_tags=["dp"], min_confidence=0.0
        )
        names = {item["tag"] for item in suggestions}
        assert "dp" not in names

    def test_min_confidence_validation(self, manager):
        with pytest.raises(ValueError, match="min_confidence"):
            manager.recommend_tags("title", "description", min_confidence=1.5)
        with pytest.raises(ValueError, match="min_confidence"):
            manager.recommend_tags("title", "description", min_confidence=-0.1)

    def test_no_match_returns_empty(self, manager):
        suggestions = manager.recommend_tags("zzz", "qqq", min_confidence=0.99)
        assert suggestions == []


class TestNormalizeDataset:
    def test_normalize_dataset_writes_output_and_report(self, tmp_path):
        dataset = tmp_path / "problems.json"
        dataset.write_text(
            json.dumps(
                [
                    {
                        "problem_id": "p1",
                        "title": "DP problem",
                        "description": "dynamic programming",
                        "difficulty": "easy",
                        "tags": ["DP"],
                        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        manager = TagManager()
        report = manager.normalize_dataset(
            str(dataset),
            output_path=str(tmp_path / "normalized.json"),
        )
        assert report
        assert (tmp_path / "normalized.json").exists()
        normalized = json.loads((tmp_path / "normalized.json").read_text(encoding="utf-8"))
        assert normalized[0]["problem_id"] == "p1"


class TestCustomMapping:
    def test_missing_mapping_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Tag mapping file not found"):
            TagManager(tmp_path / "no-such-mapping.yaml")

    def test_non_mapping_yaml_raises(self, tmp_path):
        path = tmp_path / "mapping.yaml"
        path.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            TagManager(path)

    def test_custom_keywords_are_merged_and_used(self, tmp_path):
        path = tmp_path / "mapping.yaml"
        path.write_text(
            "keywords:\n  graph theory:\n    - shortest path\n",
            encoding="utf-8",
        )
        manager = TagManager(path)
        suggestions = manager.recommend_tags("shortest path problem", "", min_confidence=0.0)
        assert any(item["tag"] == "graph theory" for item in suggestions)

    def test_aliases_section_merged(self, tmp_path):
        path = tmp_path / "mapping.yaml"
        path.write_text('aliases:\n  "greedy algorithm": greedy\n', encoding="utf-8")
        manager = TagManager(path)
        assert "greedy" in manager.normalize_tags(["Greedy Algorithm"])


def test_tags_section_merged_with_builtin(tmp_path):
    """The tags section merges aliases/keywords into builtin definitions."""
    path = tmp_path / "mapping.yaml"
    path.write_text(
        "tags:\n"
        "  dynamic-programming:\n"
        "    aliases: [DP practice]\n"
        "    keywords: [state compression]\n",
        encoding="utf-8",
    )
    manager = TagManager(path)
    assert manager.normalize_tags(["DP practice"]) == ["dynamic-programming"]
    assert manager.normalize_tags(["dp"]) == manager.normalize_tags(["DP practice"])
    suggestions = manager.recommend_tags("state compression trick", "", min_confidence=0.0)
    assert any(item["tag"] == "dynamic-programming" for item in suggestions)
