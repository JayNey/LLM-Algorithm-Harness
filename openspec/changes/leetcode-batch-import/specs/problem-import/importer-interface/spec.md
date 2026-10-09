# problem-import/importer-interface Delta Specification

## MODIFIED Requirements

### Requirement: 导入器必须实现标准接口

所有题库导入器 SHALL 继承自 `ProblemImporter` 抽象基类，实现以下方法：
- `fetch_problems(source, **filters)` — 从来源拉取或读取原始题目数据，支持可选的过滤参数（tags, difficulty, limit）
- `transform_to_schema(raw_data)` — 将原始数据转换为 `Problem` schema
- `validate_problems(problems)` — 校验转换后的题目列表
- `detect_duplicates(problems, existing_problems)` — 检测与已有题目的重复
- `generate_report(results)` — 生成导入报告
- `persist_dataset(problems, target_path)` — 原子写入数据集

#### Scenario: 本地 JSON 导入器实现接口

- **WHEN** 用户使用 `LocalJsonImporter` 导入本地 JSON 文件
- **THEN** 系统通过标准接口方法完成拉取、转换、校验、去重、报告生成和持久化

#### Scenario: 新平台适配器实现接口

- **WHEN** 开发者为新平台（如 LeetCode）创建适配器
- **THEN** 适配器继承 `ProblemImporter` 并实现所有抽象方法，复用标准校验和去重逻辑

#### Scenario: 批量导入器接受过滤参数

- **WHEN** 用户使用 `LeetCodeImporter` 批量导入题目，传入 `tags=['dynamic-programming'], difficulty='medium', limit=10`
- **THEN** `fetch_problems()` 方法接受这些过滤参数，返回符合条件的题目列表

## ADDED Requirements

### Requirement: 批量导入器支持过滤参数

支持批量导入的导入器（LeetCode, Codeforces, LiveCodeBench）SHALL 在 `fetch_problems()` 方法中接受可选的过滤参数：
- `tags: list[str] | None` — 标签列表
- `difficulty: str | None` — 难度级别（easy, medium, hard）
- `limit: int | None` — 限制题目数量

#### Scenario: LeetCode 导入器应用过滤参数

- **WHEN** `LeetCodeImporter.fetch_problems(source=None, tags=['graph'], difficulty='medium', limit=5)` 被调用
- **THEN** 系统通过 `problemsetQuestionList` GraphQL 查询获取符合条件的题目列表，再逐题抓取详情

#### Scenario: 单题导入忽略过滤参数

- **WHEN** `LeetCodeImporter.fetch_problems(source='two-sum', tags=['array'], limit=10)` 被调用
- **THEN** 系统只导入 'two-sum' 这一个题目，忽略 tags 和 limit 参数

### Requirement: 批量抓取支持部分失败

批量导入过程中，题目列表查询成功但单个题目详情抓取失败时，导入器 SHALL 继续处理其他题目，并记录失败项。

#### Scenario: 批量导入中单题抓取失败

- **WHEN** 批量导入 10 个 LeetCode 题目，其中 1 个题目详情抓取返回 404（题目已删除或受限）
- **THEN** 系统成功导入 9 个题目，报告中列出 1 个失败项及其错误原因

#### Scenario: 列表查询失败终止导入

- **WHEN** 批量导入时，`problemsetQuestionList` 查询失败（网络错误或限流）
- **THEN** 系统抛出错误并终止导入，不写入任何数据

### Requirement: 批量导入遵守限流策略

批量导入器 SHALL 复用现有的重试、退避和限流处理逻辑，适配批量场景的多次请求。

#### Scenario: 批量导入遇到 429 限流

- **WHEN** 批量导入过程中某个题目详情请求返回 429
- **THEN** 系统按退避策略重试该请求，失败后记录该题目失败并继续其他题目

#### Scenario: 批量导入超时重试

- **WHEN** 批量导入过程中某个题目详情请求超时
- **THEN** 系统按配置的重试次数重试，超过重试次数后记录失败并继续
