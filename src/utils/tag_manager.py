"""Tag normalization and recommendation utilities.

The manager keeps platform-specific aliases at the dataset boundary.  It is
deliberately deterministic: recommendations are generated from the title and
description with configured keywords, so a normalization preview never sends
problem data to an LLM or changes the dataset implicitly.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from src.utils.logging import get_logger

logger = get_logger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAPPING_PATH = PROJECT_ROOT / "config" / "tag_mapping.yaml"


class TagManager:
    """Normalize tags and suggest missing tags using a YAML mapping."""

    def __init__(self, mapping_path: str | Path | None = None):
        self.mapping_path = Path(mapping_path) if mapping_path else DEFAULT_MAPPING_PATH
        self._mapping = self._load_mapping_with_defaults(self.mapping_path)
        self._aliases: dict[str, str] = {}
        self._keywords: dict[str, tuple[str, ...]] = {}
        self._build_indexes(self._mapping)

    @staticmethod
    def _load_mapping(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Tag mapping file not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Tag mapping must be a YAML mapping")
        return payload

    @classmethod
    def _load_mapping_with_defaults(cls, path: Path) -> dict[str, Any]:
        """Load project defaults and merge a user mapping on top when provided."""
        custom = cls._load_mapping(path)
        if path.resolve() == DEFAULT_MAPPING_PATH.resolve():
            return custom
        if not DEFAULT_MAPPING_PATH.exists():
            return custom
        base = cls._load_mapping(DEFAULT_MAPPING_PATH)
        merged = deepcopy(base)
        for section in ("tags", "canonical_tags"):
            if section not in custom:
                continue
            target = merged.setdefault(section, {})
            for canonical, definition in custom[section].items():
                if (
                    isinstance(target.get(canonical), dict)
                    and isinstance(definition, dict)
                ):
                    current = target[canonical]
                    for key in ("aliases", "keywords"):
                        if key in definition:
                            values = cls._as_strings(current.get(key)) + cls._as_strings(
                                definition[key]
                            )
                            current[key] = list(dict.fromkeys(values))
                else:
                    target[canonical] = definition
        for section in ("aliases", "keywords"):
            if section in custom:
                merged.setdefault(section, {}).update(custom[section])
        merged.update({key: value for key, value in custom.items() if key not in {
            "tags", "canonical_tags", "aliases", "keywords"
        }})
        return merged

    @staticmethod
    def _key(value: str) -> str:
        """Create a case-insensitive key while preserving CJK characters."""
        normalized = unicodedata.normalize("NFKC", str(value)).casefold().strip()
        normalized = re.sub(r"[\s_]+", "-", normalized)
        normalized = re.sub(r"[^\w\-\u3400-\u9fff]", "", normalized)
        return normalized.strip("-")

    @classmethod
    def _as_strings(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        raise ValueError("Tag aliases and keywords must be strings or lists")

    def _build_indexes(self, payload: dict[str, Any]) -> None:
        """Build alias and keyword indexes from built-in and custom mapping data."""
        definitions = payload.get("tags", payload.get("canonical_tags", {}))
        if not isinstance(definitions, dict):
            raise ValueError("Tag mapping 'tags' must be a mapping")

        for canonical, definition in definitions.items():
            canonical_name = str(canonical).strip()
            if not canonical_name:
                continue
            if isinstance(definition, dict):
                aliases = self._as_strings(definition.get("aliases"))
                keywords = self._as_strings(definition.get("keywords"))
            else:
                aliases = self._as_strings(definition)
                keywords = []
            self._aliases[self._key(canonical_name)] = canonical_name
            for alias in aliases:
                self._aliases[self._key(alias)] = canonical_name
            self._keywords[canonical_name] = tuple(
                dict.fromkeys([canonical_name, *keywords, *aliases])
            )

        # A compact aliases section is convenient for project-local additions.
        aliases = payload.get("aliases", {})
        if aliases:
            if not isinstance(aliases, dict):
                raise ValueError("Tag mapping 'aliases' must be a mapping")
            for alias, canonical in aliases.items():
                canonical_name = str(canonical).strip()
                self._aliases[self._key(str(alias))] = canonical_name
                self._aliases.setdefault(self._key(canonical_name), canonical_name)
                self._keywords.setdefault(canonical_name, (canonical_name,))

        # Custom files can provide extra phrases independently of tag aliases.
        keywords = payload.get("keywords", {})
        if keywords:
            if not isinstance(keywords, dict):
                raise ValueError("Tag mapping 'keywords' must be a mapping")
            for canonical, phrases in keywords.items():
                canonical_name = str(canonical).strip()
                self._aliases.setdefault(self._key(canonical_name), canonical_name)
                current = list(self._keywords.get(canonical_name, (canonical_name,)))
                current.extend(self._as_strings(phrases))
                self._keywords[canonical_name] = tuple(dict.fromkeys(current))

    def normalize_tag(self, tag: str) -> str:
        """Return the canonical name for an alias, or a stable fallback slug."""
        if not isinstance(tag, str):
            raise TypeError("Tags must be strings")
        raw = tag.strip()
        if not raw:
            return ""
        mapped = self._aliases.get(self._key(raw))
        if mapped:
            return mapped
        return self._key(raw)

    def normalize_tags(self, tags: list[str] | None) -> list[str]:
        """Normalize tags, remove empty values, and preserve first-seen order."""
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in tags or []:
            canonical = self.normalize_tag(tag)
            if canonical and canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
        return normalized

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        phrase_key = phrase.casefold().strip()
        if not phrase_key:
            return False
        if re.search(r"[\u3400-\u9fff]", phrase_key):
            return phrase_key in text
        escaped = re.escape(phrase_key).replace(r"\ ", r"\s+")
        return re.search(rf"(?<![\w-]){escaped}(?![\w-])", text) is not None

    def recommend_tags(
        self,
        title: str,
        description: str,
        existing_tags: list[str] | None = None,
        min_confidence: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Suggest canonical tags from title/description keyword matches.

        A title match receives more weight than a description-only match. The
        confidence score is intentionally conservative and deterministic; users
        still explicitly confirm suggestions before they are written.
        """
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        title_text = unicodedata.normalize("NFKC", title or "").casefold()
        description_text = unicodedata.normalize("NFKC", description or "").casefold()
        existing = set(self.normalize_tags(existing_tags))
        suggestions: list[dict[str, Any]] = []
        matched_by_tag: dict[str, tuple[list[str], list[str]]] = {}

        for canonical, phrases in self._keywords.items():
            if canonical in existing:
                continue
            title_matches = [p for p in phrases if self._contains_phrase(title_text, p)]
            description_matches = [
                p for p in phrases if p not in title_matches and self._contains_phrase(description_text, p)
            ]
            if not title_matches and not description_matches:
                continue
            matched_by_tag[canonical] = (title_matches, description_matches)

        # Prefer a specific phrase such as "segment tree" over a generic tag
        # keyword such as "tree" when both occur in the same text.
        all_matches = [
            (canonical, phrase)
            for canonical, (title_matches, description_matches) in matched_by_tag.items()
            for phrase in [*title_matches, *description_matches]
        ]

        def is_dominated(canonical: str, phrase: str) -> bool:
            return any(
                other_canonical != canonical
                and phrase.casefold() != other_phrase.casefold()
                and phrase.casefold() in other_phrase.casefold()
                for other_canonical, other_phrase in all_matches
            )

        for canonical, (title_matches, description_matches) in matched_by_tag.items():
            matches = [*title_matches, *description_matches]
            if matches and all(is_dominated(canonical, phrase) for phrase in matches):
                continue
            score = min(0.99, 0.76 + (0.12 if title_matches else 0.0) + 0.04 * min(len(description_matches), 3))
            if score < min_confidence:
                continue
            matches = title_matches + description_matches
            suggestions.append(
                {
                    "tag": canonical,
                    "confidence": round(score, 2),
                    "matched_keywords": matches,
                    "reason": "title/description keyword match",
                }
            )

        return sorted(suggestions, key=lambda item: (-item["confidence"], item["tag"]))

    def normalize_dataset(
        self,
        dataset_path: str | Path,
        output_path: str | Path | None = None,
        apply_recommendations: bool = False,
        min_confidence: float = 0.8,
    ) -> dict[str, Any]:
        """Create a normalization report and optionally write a new dataset."""
        source = Path(dataset_path)
        if not source.exists():
            raise FileNotFoundError(f"Dataset file not found: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Dataset must be a JSON array")

        normalized_payload = deepcopy(payload)
        entries: list[dict[str, Any]] = []
        unknown_tags: set[str] = set()
        changed_problems = 0
        suggestion_count = 0
        applied_suggestion_count = 0
        all_suggestions: list[dict[str, Any]] = []
        before_counts: Counter[str] = Counter()
        after_counts: Counter[str] = Counter()

        for index, problem in enumerate(payload):
            if not isinstance(problem, dict):
                raise ValueError(f"Problem at index {index} must be a mapping")
            original_tags = problem.get("tags", [])
            if not isinstance(original_tags, list):
                raise ValueError(f"Problem at index {index} has non-list tags")
            normalized_tags = self.normalize_tags(original_tags)
            before_counts.update(str(tag) for tag in original_tags if str(tag).strip())
            for original in original_tags:
                if self._key(str(original)) not in self._aliases:
                    unknown_tags.add(str(original))
            suggestions = self.recommend_tags(
                str(problem.get("title", "")),
                str(problem.get("description", "")),
                normalized_tags,
                min_confidence=min_confidence,
            )
            suggestion_count += len(suggestions)
            all_suggestions.extend(
                {"problem_id": problem.get("problem_id", f"index-{index}"), **suggestion}
                for suggestion in suggestions
            )
            final_tags = list(normalized_tags)
            if apply_recommendations:
                final_tags.extend(item["tag"] for item in suggestions)
                applied_suggestion_count += len(suggestions)
            changed = final_tags != original_tags
            if changed:
                changed_problems += 1
            normalized_payload[index]["tags"] = final_tags
            after_counts.update(final_tags)
            entries.append(
                {
                    "problem_id": problem.get("problem_id", f"index-{index}"),
                    "original_tags": original_tags,
                    "normalized_tags": final_tags,
                    "suggestions": suggestions,
                    "changed": changed,
                }
            )

        written_path = None
        if output_path:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(normalized_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written_path = str(target)

        report = {
            "dataset": str(source),
            "mapping": str(self.mapping_path),
            "problem_count": len(payload),
            "changed_problem_count": changed_problems,
            "suggestion_count": suggestion_count,
            "applied_suggestion_count": applied_suggestion_count,
            "unknown_tags": sorted(unknown_tags),
            "tag_counts_before": dict(sorted(before_counts.items())),
            "tag_counts_after": dict(sorted(after_counts.items())),
            "apply_recommendations": apply_recommendations,
            "min_confidence": min_confidence,
            "normalized_dataset": written_path,
            "problems": entries,
            "suggestions": all_suggestions,
        }
        logger.info(
            "tag_normalization_completed",
            dataset=str(source),
            problems=len(payload),
            changed=changed_problems,
            suggestions=suggestion_count,
        )
        return report
