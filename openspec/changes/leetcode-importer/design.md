# 设计：LeetCode 公开题目导入

## Decisions

1. **使用公开 GraphQL 题目查询。** 适配器向 `https://leetcode.com/graphql` 发送 `questionData(titleSlug: ...)` 查询，默认只允许 `leetcode.com`/`www.leetcode.com` 主机；其他域名明确报 unsupported source。
2. **网络边界可控。** 请求设置连接/读取超时、有限重试和指数退避；429、403、404、GraphQL errors 和网络异常转成可读的导入失败，不循环重试。
3. **题面清洗保守。** 保留代码块、换行、公式上下标和约束含义，去除展示层 HTML；清洗器使用离线夹具验证，不依赖浏览器或第三方 DOM 包。
4. **不猜测公开样例。** 只有同时识别输入和期望输出的样例才生成 `public_test_cases`。否则生成 `needs_manual_completion=true` 和人工补全说明，预览中展示原因，不写入伪造输入/答案。
5. **签名适配有限。** 从 Python code snippet 提取普通函数或 `Solution.method` 入口；缺失或复杂签名标记人工补全。链表、树和交互协议继续由 Issue #7 的 `unsupported_reason` 边界处理。
6. **复用现有导入生命周期。** LeetCode importer 只负责 fetch/transform，重复检测、预览确认、严格模式、报告和原子持久化仍由现有 `ProblemImporter`/CLI 完成。

## Error handling

- URL 解析失败：提示只能使用题目 URL 或 slug。
- 不支持域名：返回 source unsupported。
- 题目不存在或受限：保留失败原因，不产生 Problem。
- 题面字段缺失或样例无法可靠解析：生成可预览的人工补全记录。
- 网络错误：返回可重试的失败项，离线测试不触发网络。
