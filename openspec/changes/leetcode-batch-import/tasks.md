# 实现任务清单

## 1. GraphQL 查询与批量模式检测

- [x] 1.1 在 `src/importers/leetcode.py` 中增加 `PROBLEMSET_QUERY` 常量，包含 `problemsetQuestionList` GraphQL 查询，并验证查询字符串格式正确
- [x] 1.2 修改 `LeetCodeImporter.__init__()` 增加 `batch_delay_seconds` 参数（默认 0.2），并验证参数可正确传递
- [x] 1.3 修改 `fetch_problems()` 方法签名为 `fetch_problems(source=None, tags=None, difficulty=None, limit=None)`，保持向后兼容，并验证单题导入调用 `fetch_problems('two-sum')` 不受影响

## 2. 批量查询实现

- [x] 2.1 实现 `_fetch_question_list(tags, difficulty, limit)` 方法，调用 `problemsetQuestionList` GraphQL 查询，返回题目元数据列表（slug、题号、难度、标签），并验证离线夹具测试通过
- [x] 2.2 在 `_fetch_question_list()` 中处理 LeetCode 难度枚举（easy→EASY, medium→MEDIUM, hard→HARD），并验证大小写转换正确
- [x] 2.3 在 `_fetch_question_list()` 中增加响应字段存在性检查，缺失 `questions` 或 `titleSlug` 时抛出明确错误，并验证错误消息清晰
- [x] 2.4 在 `_fetch_question_list()` 中复用现有的重试、退避和限流处理逻辑，并验证 429 响应触发重试

## 3. 逐题详情抓取

- [x] 3.1 从现有 `fetch_problems()` 中提取单题详情抓取逻辑到新方法 `_fetch_question_data(slug)`，并验证单题导入测试仍然通过
- [x] 3.2 在批量模式的 `fetch_problems()` 中调用 `_fetch_question_list()` 获取题目列表，再逐题调用 `_fetch_question_data()`，并验证返回多题列表
- [x] 3.3 在逐题抓取循环中增加请求间延迟 `self.sleep(self.batch_delay_seconds)`，并验证延迟生效（通过 mock sleep 检查调用次数）
- [x] 3.4 在逐题抓取中捕获单题失败，记录到 `transform_failures` 并继续其他题目，并验证部分失败场景测试通过

## 4. CLI 参数传递

- [x] 4.1 检查 `src/main.py` 的 `handle_import()` 函数，确认是否已将 `--tags`、`--import-difficulty`、`--import-limit` 传递给导入器，如未传递则增加参数提取和传递逻辑，并验证参数正确传递到 `fetch_problems()`
- [x] 4.2 在 CLI 层增加批量导入参数验证：`--source leetcode` 批量模式需要至少一个过滤参数（tags、difficulty），并验证缺少参数时返回明确错误
- [x] 4.3 增加批量导入进度输出：在逐题抓取时 `print(f"Fetching problem {idx+1}/{total}: {slug}")`，并验证输出格式正确

## 5. 测试与验证

- [x] 5.1 增加 `problemsetQuestionList` 查询的离线响应夹具（至少包含 3 个题目的列表响应），并验证夹具格式符合实际 API 响应
- [x] 5.2 增加单元测试：批量查询返回多题列表，并验证测试覆盖 tags + difficulty + limit 组合
- [x] 5.3 增加单元测试：批量模式下单题详情抓取失败，部分成功导入其他题目，并验证 `transform_failures` 正确记录失败项
- [x] 5.4 增加单元测试：单题导入（URL/slug）忽略批量参数，保持现有行为，并验证行为兼容
- [x] 5.5 运行全量测试套件 `pytest tests/` 并确认所有测试通过
- [x] 5.6 运行 linter 和类型检查（`mypy src/importers/leetcode.py` 或项目配置的检查命令），并确认无警告

## 6. 文档更新

- [ ] 6.1 更新 README 或导入文档，增加 LeetCode 批量导入示例（按标签、按难度、按数量限制），并验证示例命令格式正确
- [ ] 6.2 在文档中说明批量导入的限流风险和建议的 `limit` 值（≤ 50），并验证用户可理解风险说明
