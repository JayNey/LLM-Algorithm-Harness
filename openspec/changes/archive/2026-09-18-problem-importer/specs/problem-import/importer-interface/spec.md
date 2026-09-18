## Purpose

定义可扩展的题库导入器接口，规范从不同来源（本地 JSON、LeetCode、LiveCodeBench 等）导入题目的标准流程，包括拉取、转换、校验、去重、报告生成和原子持久化。

## ADDED Requirements

### Requirement: 导入器必须实现标准接口

所有题库导入器 SHALL 继承自 `ProblemImporter` 抽象基类，实现以下方法：
- `fetch_problems()` — 从来源拉取或读取原始题目数据
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

### Requirement: 题目识别基于平台和稳定题号

导入器 SHALL 使用 `source_platform` 和 `source_problem_id` 组合唯一识别题目，用于去重检测。

#### Scenario: 检测相同平台的重复题目

- **WHEN** 导入的题目与已有题目的 `source_platform` 和 `source_problem_id` 完全相同
- **THEN** 系统标记为重复，并根据更新策略决定是跳过还是覆盖

#### Scenario: 不同平台的相同题目不视为重复

- **WHEN** 两个题目的 `source_platform` 不同但 `source_problem_id` 相同
- **THEN** 系统视为不同题目，允许同时存在

### Requirement: 原子写入数据集

数据集持久化 SHALL 使用原子操作，确保写入失败时不损坏原文件。

#### Scenario: 原子写入成功

- **WHEN** 导入器持久化数据集到目标路径
- **THEN** 系统先写入临时文件，写入成功后原子重命名替换原文件

#### Scenario: 写入失败保留原文件

- **WHEN** 写入临时文件或重命名操作失败
- **THEN** 系统保留原始数据集文件不变，抛出明确的错误信息

### Requirement: 单题失败不影响其他题目

导入过程 SHALL 采用部分成功模式：单个题目解析或校验失败不阻止其他题目的导入。

#### Scenario: 批量导入中部分题目失败

- **WHEN** 批量导入 10 个题目，其中 2 个解析失败
- **THEN** 系统成功导入 8 个有效题目，报告中列出 2 个失败项及其错误原因

#### Scenario: 所有题目失败时抛出错误

- **WHEN** 批量导入的所有题目都解析或校验失败
- **THEN** 系统抛出错误，不写入任何数据
