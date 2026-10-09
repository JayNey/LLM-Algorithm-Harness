# 设计文档：LeetCode 批量导入

## Context

当前 `LeetCodeImporter` 只支持通过 `questionData` GraphQL 查询导入单个题目。`fetch_problems()` 接受单个 URL 或 slug，返回单元素列表。CLI 的 `--tags`、`--import-difficulty`、`--import-limit` 参数已存在，但只对 Codeforces 和 LiveCodeBench 生效。

本次变更需要：
1. 在 `LeetCodeImporter` 中增加批量查询能力
2. 使批量参数对 `--source leetcode` 生效
3. 保持单题 URL/slug 导入的现有行为完全兼容

见 proposal.md 了解动机。

## Goals / Non-Goals

**Goals:**
- 使用 LeetCode 的 `problemsetQuestionList` GraphQL 查询支持按标签和难度过滤题目列表
- 批量模式下先获取题目列表（slug、题号、难度、标签），再逐题复用现有 `questionData` 查询抓取详情
- 复用现有的重试、退避、限流处理和部分失败机制
- 单题和批量模式在同一个 `LeetCodeImporter` 类中共存，通过输入参数区分
- CLI 参数传递机制无需改动（假设现有框架已支持将参数传递给导入器）

**Non-Goals:**
- 不处理 LeetCode 付费题目或需要登录的内容
- 不实现分页（首次支持单次查询返回的题目数，LeetCode API 通常支持 limit + skip，可后续扩展）
- 不增加进度条渲染库（使用简单的 print 输出）

## Decisions

### 1. 批量查询使用 `problemsetQuestionList` GraphQL 查询

**选择：** 使用 LeetCode 公开的 `problemsetQuestionList` 查询，支持 `filters: { tags, difficulty }` 和分页参数 `limit`、`skip`。

**理由：**
- LeetCode 官方 GraphQL API 的标准查询，用于题库列表页
- 返回题目元数据（questionFrontendId、titleSlug、difficulty、topicTags），足以构建题目列表
- 支持标签数组（如 `["dynamic-programming", "graph"]`）和难度枚举（EASY/MEDIUM/HARD）

**替代方案：**
- 爬取 HTML 页面：不稳定，容易受页面结构变化影响，违反 robots.txt
- 使用第三方 API（如 LeetCode-cn API）：依赖外部服务，可用性无保证

**GraphQL 查询示例：**
```graphql
query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
  problemsetQuestionList(
    categorySlug: $categorySlug
    limit: $limit
    skip: $skip
    filters: $filters
  ) {
    total
    questions {
      questionFrontendId
      titleSlug
      title
      difficulty
      topicTags { name slug }
    }
  }
}
```

变量示例：
```json
{
  "categorySlug": "",
  "limit": 20,
  "skip": 0,
  "filters": {
    "tags": ["dynamic-programming"],
    "difficulty": "MEDIUM"
  }
}
```

### 2. 批量模式检测：有过滤参数且无 `source` URL/slug

**选择：** `fetch_problems(source, **filters)` 签名变更：
- `source` 参数可选（保留兼容性）
- 新增 `tags`, `difficulty`, `limit` 关键字参数
- 当 `source` 为空或 None 且存在任一过滤参数时，进入批量模式
- 当 `source` 为 URL 或 slug 时，忽略过滤参数，保持单题导入行为

**理由：**
- 向后兼容：现有单题调用 `fetch_problems('two-sum')` 不受影响
- 明确的模式区分：有 source 就是单题，无 source 但有过滤参数就是批量
- 避免引入新方法（如 `fetch_batch_problems`），保持接口简洁

**替代方案：**
- 新增 `fetch_batch_problems()` 方法：增加接口复杂度，需修改基类
- 通过 `source` 特殊值（如 `"batch"`）触发批量模式：不直观，容易误用

### 3. 逐题详情抓取复用现有 `questionData` 查询

**选择：** 批量模式流程：
1. 调用 `problemsetQuestionList` 获取题目列表（slug、题号、难度、标签）
2. 对每个 slug，调用现有的 `_fetch_question_data(slug)` 方法（内部提取现有代码）抓取详情
3. 复用现有的重试、退避、限流处理
4. 单题失败时记录到 `transform_failures`，不阻止其他题目

**理由：**
- 代码复用：详情抓取逻辑已存在且经过测试
- 限流容错：现有重试机制支持 429 响应
- 部分成功：符合 `ProblemImporter` 接口规范

**风险：** N+1 请求模式可能触发 LeetCode 限流
**缓解措施：**
- 复用现有的 `retries` 和 `backoff_seconds` 参数
- 在每次详情请求间增加可选的延迟（如 `batch_delay_seconds`，默认 0.2s）
- 记录失败题目，允许用户后续重试

### 4. CLI 参数传递：假设现有框架支持

**选择：** 假设 `src/main.py` 的导入命令处理逻辑已将 `--tags`、`--import-difficulty`、`--import-limit` 传递给导入器。

**验证点：** 检查 `handle_import()` 函数是否将这些参数传递给 `importer.fetch_problems()`。如果不支持，需在 `handle_import()` 中增加参数传递逻辑。

**假设不成立时的修改：**
```python
# src/main.py, handle_import() 函数
filters = {}
if args.tags:
    filters['tags'] = args.tags
if args.import_difficulty:
    filters['difficulty'] = args.import_difficulty
if args.import_limit:
    filters['limit'] = args.import_limit

raw_data = importer.fetch_problems(args.input, **filters)
```

## Risks / Trade-offs

### [风险] LeetCode 限流导致批量导入失败
**缓解措施：**
- 使用现有的重试和退避逻辑
- 增加可选的请求间延迟（`batch_delay_seconds`）
- 记录失败题目到报告中，允许用户后续重试失败项
- 文档中说明批量导入的限流风险和建议的 `limit` 值（如 ≤ 50）

### [风险] `problemsetQuestionList` API 变更或返回字段不稳定
**缓解措施：**
- 增加离线响应夹具覆盖 `problemsetQuestionList` 查询
- 在 `_fetch_question_list()` 中增加字段存在性检查，缺失时抛出明确错误
- 监控 LeetCode API 变更（无自动化手段，依赖社区反馈）

### [权衡] N+1 请求模式 vs 单次批量详情查询
**选择：** N+1 模式（列表查询 + 逐题详情查询）
**理由：**
- LeetCode GraphQL API 不提供批量详情查询（`questionData` 只接受单个 `titleSlug`）
- N+1 是唯一可行方案
**影响：** 批量导入 20 题需要 21 次请求（1 次列表 + 20 次详情），耗时较长

### [权衡] 不实现进度条库，使用简单输出
**选择：** 使用 `print()` 输出进度，格式：`Fetching problem 3/20: two-sum`
**理由：**
- 不引入新依赖（如 `tqdm`）
- 足以满足用户对批量导入进度的基本需求
**影响：** 进度输出不如进度条直观，但避免依赖膨胀

## Migration Plan

无需迁移，向后兼容：
- 现有单题导入调用不受影响
- 新增批量功能为可选特性，用户可选择使用

**部署步骤：**
1. 合并代码到主分支
2. 运行全量测试（包括新增的批量导入测试）
3. 更新文档，增加批量导入示例
4. 发布新版本

**回滚策略：**
- 如批量导入引入 bug，可临时禁用批量参数（CLI 层面拒绝 `--source leetcode` + 批量参数组合）
- 回滚代码到上一版本

## Open Questions

无需推迟的问题。所有技术决策已明确，可直接进入任务分解和实现。
