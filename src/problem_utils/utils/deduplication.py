"""
题目去重工具模块

提供相似度检测和指纹匹配功能，用于识别和合并重复题目。
"""

from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def compute_similarity(problems: list[dict[str, Any]]) -> np.ndarray:
    """
    计算题目之间的文本相似度矩阵

    使用 TF-IDF 向量化和余弦相似度算法。

    Args:
        problems: 题目列表，每个题目包含 title 和 description 字段

    Returns:
        相似度矩阵 (n x n)，其中 matrix[i][j] 表示题目 i 和 j 的相似度
    """
    if not problems:
        return np.array([])

    # 组合标题和描述作为文本特征
    texts = [f"{p.get('title', '')} {p.get('description', '')}" for p in problems]

    # 使用 TF-IDF 向量化
    vectorizer = TfidfVectorizer(max_features=1000, stop_words="english", ngram_range=(1, 2))
    tfidf_matrix = vectorizer.fit_transform(texts)

    # 计算余弦相似度
    similarity_matrix = cosine_similarity(tfidf_matrix)

    return similarity_matrix  # type: ignore[no-any-return]


def find_similar_pairs(
    problems: list[dict[str, Any]], threshold: float = 0.9
) -> list[tuple[int, int, float]]:
    """
    基于相似度阈值检测相似题目对

    Args:
        problems: 题目列表
        threshold: 相似度阈值，默认 0.9

    Returns:
        相似题目对列表，每个元素为 (index1, index2, similarity)
    """
    similarity_matrix = compute_similarity(problems)

    if similarity_matrix.size == 0:
        return []

    pairs = []
    n = len(problems)

    # 只检查上三角矩阵，避免重复
    for i in range(n):
        for j in range(i + 1, n):
            sim = similarity_matrix[i][j]
            if sim > threshold:
                pairs.append((i, j, float(sim)))

    return pairs


def generate_fingerprint(problem: dict[str, Any]) -> str | None:
    """
    基于 source_platform 和 source_problem_id 生成唯一指纹

    Args:
        problem: 题目字典

    Returns:
        指纹字符串，如果缺少来源信息则返回 None
    """
    source_platform = problem.get("source_platform")
    source_problem_id = problem.get("source_problem_id")

    if not source_platform or not source_problem_id:
        return None

    return f"{source_platform}:{source_problem_id}"


def find_fingerprint_duplicates(problems: list[dict[str, Any]]) -> list[list[int]]:
    """
    检测完全相同的题目（基于指纹匹配）

    Args:
        problems: 题目列表

    Returns:
        重复组列表，每组包含具有相同指纹的题目索引
    """
    fingerprint_map: dict[str, list[int]] = {}

    for idx, problem in enumerate(problems):
        fingerprint = generate_fingerprint(problem)
        if fingerprint:
            if fingerprint not in fingerprint_map:
                fingerprint_map[fingerprint] = []
            fingerprint_map[fingerprint].append(idx)

    # 只返回有重复的组（长度 > 1）
    duplicate_groups = [indices for indices in fingerprint_map.values() if len(indices) > 1]

    return duplicate_groups


def select_primary_problem(problems: list[dict[str, Any]]) -> int:
    """
    基于字段完整度选择主版本

    Args:
        problems: 题目列表（通常是重复组）

    Returns:
        主版本的索引
    """
    if not problems:
        raise ValueError("Cannot select primary from empty list")

    # 计算每个题目的非空字段数量
    def count_non_empty_fields(problem: dict[str, Any]) -> int:
        count = 0
        for key, value in problem.items():
            if value is not None and value != "" and value != []:
                count += 1
        return count

    max_completeness = -1
    primary_idx = 0

    for idx, problem in enumerate(problems):
        completeness = count_non_empty_fields(problem)
        if completeness > max_completeness:
            max_completeness = completeness
            primary_idx = idx

    return primary_idx


def merge_problems(primary: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any]:
    """
    合并重复题目，保留主版本并合并列表字段

    Args:
        primary: 主版本题目
        others: 其他版本题目列表

    Returns:
        合并后的题目
    """
    merged = primary.copy()

    # 收集被合并题目的 ID
    merged_from = []
    for other in others:
        if "problem_id" in other:
            merged_from.append(other["problem_id"])

    # 合并列表字段（去重）
    list_fields = ["tags", "public_test_cases", "feedback_test_cases", "hidden_test_cases"]

    for field in list_fields:
        if field in merged:
            merged_items = merged[field].copy() if merged[field] else []

            for other in others:
                if field in other and other[field]:
                    for item in other[field]:
                        # 简单去重：对于字符串直接比较，对于字典比较序列化后的值
                        if isinstance(item, str):
                            if item not in merged_items:
                                merged_items.append(item)
                        elif isinstance(item, dict):
                            # 对于测试用例等复杂对象，使用简单的字符串比较
                            if item not in merged_items:
                                merged_items.append(item)
                        else:
                            if item not in merged_items:
                                merged_items.append(item)

            merged[field] = merged_items

    # 添加合并历史记录
    if merged_from:
        merged["merged_from"] = merged_from

    return merged
