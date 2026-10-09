# 提议：LeetCode 批量导入支持

## Why

当前 LeetCode 导入器只支持单题 URL/slug 导入，无法按标签或难度批量导入题目。已有的 `--tags`、`--import-difficulty`、`--import-limit` 参数对 Codeforces 和 LiveCodeBench 生效，但对 LeetCode 无效。用户需要手动逐个导入题目，效率低下。

添加批量导入能力可以让用户快速构建特定主题（如动态规划、图论）或难度级别的题库，与 Codeforces/LiveCodeBench 保持一致的 CLI 体验。

## What Changes

- 在 `LeetCodeImporter` 中增加 `problemsetQuestionList` GraphQL 查询，支持按标签和难度过滤题目列表
- 增加批量抓取逻辑：先获取题目列表（slug、题号、难度、标签），再逐题复用现有的 `questionData` 查询抓取详情
- 复用现有的重试、退避和 429 限流处理逻辑，针对批量场景（N+1 次请求）增强限流容错
- 使 CLI 的 `--tags`、`--import-difficulty`、`--import-limit` 参数对 `--source leetcode` 生效
- 保持现有单题 URL/slug 导入行为完全兼容
- 逐题详情抓取失败时允许部分成功，沿用现有的 `transform_failures` 和导入报告机制

## Capabilities

### New Capabilities

无新增 capability，本变更增强现有导入能力的参数支持。

### Modified Capabilities

- `problem-import/cli-commands`: `--tags`、`--import-difficulty`、`--import-limit` 参数将对 `--source leetcode` 生效，与 Codeforces/LiveCodeBench 行为一致
- `problem-import/importer-interface`: `LeetCodeImporter.fetch_problems()` 需要支持批量查询模式，返回多题列表而非单元素列表

## Impact

**受影响文件：**
- `src/importers/leetcode.py` — 增加批量查询逻辑、GraphQL query、参数处理
- `src/main.py` — 将批量参数传递给 LeetCodeImporter（可能无需改动，取决于现有参数传递机制）
- 测试夹具和单元测试 — 增加批量查询的离线响应夹具

**API 变化：**
- `LeetCodeImporter.__init__()` 可能需要接受 `tags`、`difficulty`、`limit` 参数
- `fetch_problems()` 的行为从"总是返回单元素列表"变为"返回 1 到 N 个题目"

**依赖：**
- 无新增外部依赖
- 复用现有的 requests/urllib 和 GraphQL 请求机制

**限制与风险：**
- LeetCode 可能对批量请求实施更严格的限流（N+1 请求模式）
- 需要充分测试重试/退避逻辑以处理 429 响应
- 批量导入可能耗时较长，需要提供进度反馈（可选增强）
