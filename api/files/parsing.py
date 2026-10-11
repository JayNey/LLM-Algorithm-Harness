"""Parse text data without executing uploads or echoing secret input in errors."""

import csv
import io
import json
import math
import re
from pathlib import Path
from typing import Any, cast

import yaml
from fastapi import HTTPException
from pydantic import ValidationError

from src.importers.local_json import LocalJsonImporter
from src.models import ExperimentConfig, HarnessConfig, Problem
from src.utils.secrets import redact_sensitive_data
from src.utils.validators import validate_problem_schema

EXTENSIONS = {".json", ".yaml", ".yml", ".csv"}
MIMES = {
    "application/json",
    "text/json",
    "application/yaml",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
    "text/csv",
    "application/csv",
    "text/plain",
    "application/octet-stream",
}
JSON_COLUMNS = {
    "tags",
    "test_cases",
    "public_test_cases",
    "feedback_test_cases",
    "hidden_test_cases",
    "judge_config",
    "source_metadata",
    "manual_completion_notes",
    "metadata",
}


def bad(message: str, details: Any = None) -> HTTPException:
    return HTTPException(400, {"message": message, **({"errors": details} if details else {})})


def filename_suffix(filename: str | None, content_type: str | None) -> str:
    if (
        not filename
        or len(filename) > 200
        or any(c in filename for c in "/\\:")
        or any(ord(c) < 32 for c in filename)
    ):
        raise bad("Invalid filename")
    stem = filename.split(".")[0].upper()
    if stem in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise bad("Invalid filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(415, "Only JSON, YAML, YML and CSV files are supported")
    if content_type and content_type.split(";")[0].strip().lower() not in MIMES:
        raise HTTPException(415, "Unsupported file media type")
    return suffix


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate object key")
        result[key] = value
    return result


def strict_json(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=unique_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON value")),
    )


class BoundedSafeLoader(yaml.SafeLoader):
    def __init__(self, stream: str):
        super().__init__(stream)
        self.depth = 0
        self.nodes = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        self.nodes += 1
        if self.check_event(yaml.AliasEvent) or self.depth >= 64 or self.nodes > 500000:
            raise ValueError("YAML aliases or excessive nesting are not supported")
        self.depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node: Any, deep: bool = False) -> Any:
        pairs = [
            (self.construct_object(k, deep=deep), self.construct_object(v, deep=deep))
            for k, v in node.value
        ]
        return unique_pairs(pairs)


def check_structure(data: Any) -> None:
    stack = [(data, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > 500000 or depth > 64:
            raise ValueError("Data structure exceeds parsing limits")
        if isinstance(value, dict):
            if any(not isinstance(k, str) for k in value):
                raise ValueError("Object keys must be strings")
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite value")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Unsupported data type")


def parse_file(path: Path, suffix: str, max_items: int) -> Any:
    raw = path.read_bytes()
    if (
        raw.startswith((b"MZ", b"\x7fELF", b"#!", b"PK\x03\x04", b"\xd0\xcf\x11\xe0"))
        or b"\x00" in raw
    ):
        raise bad("Binary or executable content is not supported")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise bad("File must be UTF-8 text") from None
    try:
        if suffix == ".json":
            data = strict_json(text)
        elif suffix in {".yaml", ".yml"}:
            data = yaml.load(text, Loader=BoundedSafeLoader)
        else:
            header_end = text.find("\n")
            if (header_end if header_end >= 0 else len(text)) > 65536:
                raise ValueError("CSV header exceeds limit")
            # The per-file cap already bounds memory. Increase monotonically
            # so another request cannot lower this process-wide parser limit.
            csv.field_size_limit(max(csv.field_size_limit(), len(raw)))
            reader = csv.DictReader(io.StringIO(text, newline=""))
            fields = reader.fieldnames
            if (
                not fields
                or len(fields) > 128
                or len(set(fields)) != len(fields)
                or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", f) for f in fields)
            ):
                raise ValueError("CSV requires unique named header columns")
            data = []
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("CSV row does not match header")
                data.append(row)
                if len(data) > max_items:
                    raise ValueError("Too many CSV rows")
        if not isinstance(data, (dict, list)):
            raise ValueError("File must contain an object or array")
        check_structure(data)
        return data
    except (ValueError, TypeError, RecursionError, csv.Error, yaml.YAMLError):
        raise bad("Invalid or unsafe file content") from None


def validate_problem(item: Any, csv_source: bool = False) -> Problem:
    if not isinstance(item, dict):
        raise ValueError("Problem must be an object")
    item = dict(item)
    if csv_source:
        encoding = item.pop("_harness_csv_encoding", None)
        if encoding is not None and encoding != "json-v1":
            raise ValueError("Unsupported CSV cell encoding")
        if encoding == "json-v1":
            try:
                item = {name: strict_json(value) for name, value in item.items()}
            except (ValueError, TypeError, RecursionError):
                raise ValueError("CSV JSON cell is invalid") from None
        else:
            for name in JSON_COLUMNS:
                if item.get(name):
                    try:
                        item[name] = strict_json(item[name])
                    except (ValueError, TypeError, RecursionError):
                        raise ValueError(f"Column {name} requires JSON") from None
                elif name in item:
                    del item[name]
            for name in ["source_problem_id", "constraints", "input_format", "output_format"]:
                if item.get(name) == "":
                    item.pop(name)
            if "needs_manual_completion" in item:
                value = str(item["needs_manual_completion"]).lower()
                if value not in {"true", "false", "1", "0"}:
                    raise ValueError("Invalid needs_manual_completion value")
                item["needs_manual_completion"] = value in {"true", "1"}
    check_structure(item)
    validate_problem_schema(item)
    unknown = set(item) - set(Problem.model_fields) - {"test_cases"}
    if unknown:
        raise ValidationError.from_exception_data(
            "Problem",
            [
                {"type": "extra_forbidden", "loc": (name,), "input": None}
                for name in sorted(unknown)
            ],
        )
    model = Problem.model_validate(item)
    if not model.validate_completeness():
        raise ValueError("Problem data incomplete")
    return model


def problem_error(index: int, error: Exception) -> dict[str, Any]:
    if isinstance(error, ValidationError):
        details = [
            {"field": ".".join(str(v) for v in e["loc"]), "type": e["type"]}
            for e in error.errors(include_input=False, include_context=False)
        ]
    else:
        # Only static validators are invoked; avoid their value-bearing messages.
        details = [{"field": "problem", "type": "invalid_schema"}]
    return {"index": index, "errors": details}


def transform_validated(problems: list[Problem]) -> list[Problem]:
    # The importer sees only prevalidated records, avoiding its raw-value error logs.
    return LocalJsonImporter().transform_to_schema([p.model_dump(mode="json") for p in problems])


def normalize_config(data: Any, kind: str) -> dict[str, Any]:
    model_types: dict[str, type[HarnessConfig] | type[ExperimentConfig]] = {
        "harness": HarnessConfig,
        "experiment": ExperimentConfig,
    }
    model_type = model_types.get(kind)
    if model_type is None:
        raise bad("Config type must be harness or experiment")
    try:
        model = model_type.model_validate(data)
        return cast(dict[str, Any], redact_sensitive_data(model.model_dump(mode="json")))
    except ValidationError as error:
        details = [
            {"field": ".".join(str(v) for v in e["loc"]), "type": e["type"]}
            for e in error.errors(include_input=False, include_context=False)
        ]
        raise bad("Config schema validation failed", details) from None
