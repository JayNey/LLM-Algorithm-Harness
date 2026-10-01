"""
单元测试：题目去重模块

测试相似度检测、指纹匹配和合并策略功能。
"""

import pytest

from src.problem_utils.utils.deduplication import (
    compute_similarity,
    find_fingerprint_duplicates,
    merge_problems,
    select_primary_problem,
)


class TestSimilarityDetection:
    """测试相似度检测功能"""

    def test_compute_similarity_high(self):
        """验证高相似度题目检测（相似度 > 0.9）"""
        problems = [
            {
                "title": "Two Sum",
                "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target. You may assume that each input would have exactly one solution, and you may not use the same element twice."
            },
            {
                "title": "Two Sum",
                "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target. You may assume that each input would have exactly one solution, and you may not use the same element twice."
            },
        ]

        similarity_matrix = compute_similarity(problems)

        # 验证矩阵形状正确
        assert similarity_matrix.shape == (2, 2)

        # 验证对角线为 1（自己和自己的相似度）
        assert similarity_matrix[0][0] == pytest.approx(1.0, rel=1e-5)
        assert similarity_matrix[1][1] == pytest.approx(1.0, rel=1e-5)

        # 验证高度相似（完全相同的描述应该是 1.0）
        assert similarity_matrix[0][1] > 0.9
        assert similarity_matrix[1][0] > 0.9

    def test_compute_similarity_low(self):
        """验证不同题目不被误判（相似度 <= 0.9）"""
        problems = [
            {
                "title": "Two Sum",
                "description": "Given an array of integers, return indices of two numbers that add up to a target."
            },
            {
                "title": "Binary Tree Traversal",
                "description": "Implement inorder, preorder, and postorder traversal of a binary tree."
            },
        ]

        similarity_matrix = compute_similarity(problems)

        # 验证低相似度
        assert similarity_matrix[0][1] <= 0.9
        assert similarity_matrix[1][0] <= 0.9


class TestFingerprintMatching:
    """测试指纹匹配功能"""

    def test_fingerprint_exact_match(self):
        """验证完全相同题目检测"""
        problems = [
            {
                "problem_id": "p1",
                "title": "Two Sum",
                "source_platform": "leetcode",
                "source_problem_id": "1",
            },
            {
                "problem_id": "p2",
                "title": "Two Sum Problem",
                "source_platform": "leetcode",
                "source_problem_id": "1",
            },
            {
                "problem_id": "p3",
                "title": "Three Sum",
                "source_platform": "leetcode",
                "source_problem_id": "15",
            },
        ]

        duplicate_groups = find_fingerprint_duplicates(problems)

        # 应该找到一个重复组（p1 和 p2）
        assert len(duplicate_groups) == 1
        assert set(duplicate_groups[0]) == {0, 1}

    def test_fingerprint_missing_source(self):
        """验证缺失来源信息的处理"""
        problems = [
            {
                "problem_id": "p1",
                "title": "Two Sum",
                "source_platform": "leetcode",
                "source_problem_id": "1",
            },
            {
                "problem_id": "p2",
                "title": "Two Sum",
                # 缺少 source_platform
                "source_problem_id": "1",
            },
            {
                "problem_id": "p3",
                "title": "Two Sum",
                "source_platform": "leetcode",
                # 缺少 source_problem_id
            },
        ]

        duplicate_groups = find_fingerprint_duplicates(problems)

        # 缺少来源信息的题目应该被跳过，不产生重复组
        assert len(duplicate_groups) == 0


class TestMergeStrategy:
    """测试合并策略功能"""

    def test_merge_strategy_completeness(self):
        """验证字段完整度优先策略"""
        problems = [
            {
                "problem_id": "p1",
                "title": "Two Sum",
                "description": "Short description",
            },
            {
                "problem_id": "p2",
                "title": "Two Sum",
                "description": "Detailed description",
                "difficulty": "easy",
                "tags": ["array", "hash-table"],
                "constraints": "1 <= nums.length <= 10^4",
            },
        ]

        primary_idx = select_primary_problem(problems)

        # p2 字段更完整，应该被选为主版本
        assert primary_idx == 1

    def test_merge_strategy_list_fields(self):
        """验证列表字段正确合并去重"""
        primary = {
            "problem_id": "p1",
            "title": "Two Sum",
            "tags": ["array", "hash-table"],
            "public_test_cases": [
                {"input": {"nums": [2, 7], "target": 9}, "expected_output": [0, 1]}
            ],
        }

        others = [
            {
                "problem_id": "p2",
                "title": "Two Sum",
                "tags": ["hash-table", "two-pointers"],  # hash-table 重复
                "public_test_cases": [
                    {"input": {"nums": [3, 3], "target": 6}, "expected_output": [0, 1]}
                ],
            }
        ]

        merged = merge_problems(primary, others)

        # 验证 tags 合并且去重
        assert set(merged["tags"]) == {"array", "hash-table", "two-pointers"}

        # 验证测试用例合并
        assert len(merged["public_test_cases"]) == 2

        # 验证 merged_from 字段
        assert "merged_from" in merged
        assert merged["merged_from"] == ["p2"]

