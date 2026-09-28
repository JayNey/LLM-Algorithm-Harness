"""
Enhanced error analysis (issue #52).

Classifies failures into seven categories, aggregates frequent error
patterns, and produces rule-based fix suggestions. This is a read-only
analysis layer on top of recorded results: the coarse-grained
``failure_category`` taxonomy written by the harness is unchanged.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional

CATEGORIES = [
    "syntax_error",
    "logic_error",
    "runtime_error",
    "timeout_error",
    "memory_error",
    "api_error",
    "unknown",
]

_NON_FAILURE_STATUSES = {"success", "budget_exhausted", "unsupported"}

_RUNTIME_EXCEPTIONS = (
    "IndexError",
    "KeyError",
    "TypeError",
    "AttributeError",
    "ValueError",
    "NameError",
    "ZeroDivisionError",
    "RuntimeError",
)

_SUGGESTIONS = {
    "syntax_error": ["检查缩进与语法：冒号、括号是否配对，缩进是否一致"],
    "logic_error": [
        "对拍样例：逐个手动执行公开测试，核对边界条件（空输入、单元素、极值）",
        "打印中间变量，确认循环与条件分支的行为与预期一致",
    ],
    "runtime_error": ["在本地重放失败输入，定位抛出异常的具体语句"],
    "timeout_error": ["优化算法复杂度，避免不必要的嵌套循环与重复计算"],
    "memory_error": ["避免一次性构建大对象，改用生成器或原地更新"],
    "api_error": ["模型调用失败与代码无关；检查网络、配额与模型配置后重跑"],
    "unknown": ["查看完整轨迹与失败输入，先确认失败发生在哪个环节"],
}

_EXCEPTION_SUGGESTIONS = {
    "IndexError": "检查列表边界：用 len() 确认索引在有效范围内，避免硬编码下标",
    "KeyError": "检查字典键是否存在，或改用 dict.get(key, default)",
    "TypeError": "检查参数类型与函数签名是否匹配",
    "AttributeError": "确认对象具有该属性或方法，检查类型与拼写",
    "ValueError": "检查取值范围与输入转换的合法性",
    "NameError": "检查变量名拼写与定义顺序",
    "MemoryError": "数据规模可能超出限制，改用更省内存的数据结构",
}

_SANDBOX_CATEGORY = {
    "timeout": "timeout_error",
    "memory_error": "memory_error",
    "syntax_error": "syntax_error",
    "runtime_error": "runtime_error",
}


def classify_message(message: Optional[str]) -> str:
    """Classify a single error message by exception names and keywords."""
    if not message:
        return "unknown"
    lowered = message.lower()
    if "syntaxerror" in lowered or "indentationerror" in lowered:
        return "syntax_error"
    if "memoryerror" in lowered:
        return "memory_error"
    for exception in _RUNTIME_EXCEPTIONS:
        if exception.lower() in lowered:
            return "runtime_error"
    if "assertionerror" in lowered:
        return "logic_error"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout_error"
    return "unknown"


def _terminal_category(result: Dict[str, Any]) -> Optional[str]:
    """Map sandbox terminal statuses and per-test statuses to categories."""
    final = result.get("final_result") or {}
    category = _SANDBOX_CATEGORY.get(final.get("status"))
    if category:
        return category
    for test in final.get("test_results") or []:
        category = _SANDBOX_CATEGORY.get(test.get("status"))
        if category:
            return category
        message_category = classify_message(test.get("error_message"))
        if message_category != "unknown":
            return message_category
    return None


def classify_failure(result: Dict[str, Any]) -> str:
    """Classify one recorded result into one of the seven categories.

    Priority: sandbox terminal status → API errors → logic errors →
    message regexes → unknown. ``budget_exhausted``/``unsupported`` are
    not failures and must not be classified.
    """
    if result.get("status") in _NON_FAILURE_STATUSES:
        return "unknown"
    terminal = _terminal_category(result)
    if terminal:
        return terminal
    if result.get("failure_category") == "model_error":
        return "api_error"
    if any(it.get("llm_error") for it in result.get("iterations") or []):
        return "api_error"
    if result.get("failure_category") == "wrong_answer":
        return "logic_error"
    message_category = classify_message(result.get("error_message"))
    if message_category != "unknown":
        return message_category
    return "unknown"


def normalize_message(message: Optional[str], limit: int = 120) -> str:
    """Normalize an error message for pattern aggregation."""
    if not message:
        return ""
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    first_line = re.sub(r"File \"[^\"]+\", ", "", first_line)
    first_line = re.sub(r"\d+", "N", first_line)
    return first_line[:limit]


def _first_error_message(result: Dict[str, Any]) -> str:
    final = result.get("final_result") or {}
    for test in final.get("test_results") or []:
        if not test.get("passed") and test.get("error_message"):
            return test["error_message"]
    if final.get("error_message"):
        return final["error_message"]
    if result.get("error_message"):
        return result["error_message"]
    for iteration in reversed(result.get("iterations") or []):
        if iteration.get("llm_error"):
            return iteration["llm_error"]
    return ""


def _distribution(
    failures: List[Dict[str, Any]],
    problem_info: Dict[str, Dict[str, Any]],
    attribute: str,
) -> Dict[str, Any]:
    """Category counts per group (difficulty or tag) with shares."""
    groups: Dict[str, Dict[str, Any]] = {}
    for result in failures:
        info = problem_info.get(result.get("problem_id"), {})
        values = info.get(attribute) or result.get(attribute) or []
        if isinstance(values, str):
            values = [values]
        category = result.get("_error_category", "unknown")
        for value in values or ["unknown"]:
            bucket = groups.setdefault(value, {"total": 0, "categories": {}})
            bucket["total"] += 1
            bucket["categories"][category] = bucket["categories"].get(category, 0) + 1
    for bucket in groups.values():
        bucket["categories"] = {
            name: {"count": count, "share": round(count / bucket["total"], 4)}
            for name, count in sorted(bucket["categories"].items())
        }
    return dict(sorted(groups.items()))


def suggestions_for(category: str, patterns: List[str]) -> List[str]:
    """Rule-based fix suggestions for a category, refined by exception names."""
    suggestions = list(_SUGGESTIONS.get(category, _SUGGESTIONS["unknown"]))
    if category in ("runtime_error", "unknown"):
        joined = " ".join(patterns)
        for exception, hint in _EXCEPTION_SUGGESTIONS.items():
            if exception.lower() in joined.lower() and hint not in suggestions:
                suggestions.insert(0, hint)
    return suggestions[:3]


def analyze_results(
    results: List[Dict[str, Any]],
    problem_info: Optional[Dict[str, Dict[str, Any]]] = None,
    top_n: int = 10,
) -> Dict[str, Any]:
    """Full error analysis over one set of recorded results."""
    problem_info = problem_info or {}
    failures = []
    for result in results:
        if result.get("status") in _NON_FAILURE_STATUSES:
            continue
        result = dict(result)
        result["_error_category"] = classify_failure(result)
        failures.append(result)

    categories = Counter(f["_error_category"] for f in failures)
    patterns = Counter(normalize_message(_first_error_message(f)) for f in failures)
    top_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in patterns.most_common(top_n)
        if pattern
    ]

    return {
        "total_failures": len(failures),
        "categories": {category: categories.get(category, 0) for category in CATEGORIES},
        "top_patterns": top_patterns,
        "by_difficulty": _distribution(failures, problem_info, "difficulty"),
        "by_tags": _distribution(failures, problem_info, "tags"),
        "suggestions": {
            category: suggestions_for(category, [entry["pattern"] for entry in top_patterns])
            for category in CATEGORIES
            if categories.get(category, 0) > 0
        },
    }
