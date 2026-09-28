# 提议：Codeforces 题目导入器

## Problem

当前题库只有本地 JSON、LeetCode 和 LiveCodeBench 来源，竞赛题覆盖有限。Codeforces 提供公开题目列表、rating、标签和题面样例，适合扩充 stdin/stdout 评测题库。

## Goal

- 通过公开 Codeforces API 获取题目元数据，并抓取公开题面和样例。
- 将 rating、标签、题号和题面转换到现有 `Problem` schema。
- 支持 contest、rating、标签、数量过滤，并复用现有校验、去重、预览和原子写入流程。
- 对交互题、限流、缺题面和缺样例做明确处理，不伪造隐藏测试。

## Non-goals

- 不登录、不访问提交或私有测试、不处理交互题。
- 不生成真实隐藏测试；缺失样例的题目标记人工补全。
- 不深度解析 LaTeX 或把题面答案推断为测试期望值。
