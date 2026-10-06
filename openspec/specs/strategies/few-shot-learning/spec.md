# strategies/few-shot-learning Specification

## Purpose
Few-Shot Learning 策略通过检索已解决的相似题目作为示例，构建包含示例的 prompt 来辅助 LLM 求解新的算法问题，提升求解准确率。

## Requirements

### Requirement: 策略必须支持基于标签的相似题目检索

系统 SHALL 实现基于标签 Jaccard 相似度的题目检索功能，从历史成功解答中找出相似题目作为示例。

#### Scenario: 检索到相似题目
- **WHEN** 给定一个新题目包含标签 ["array", "hash-table"]，且历史库中存在题目包含标签 ["array", "hash-table", "sorting"]
- **THEN** 系统计算 Jaccard 相似度为 2/3 = 0.67，并返回该题目作为候选示例

#### Scenario: 过滤低相似度题目
- **WHEN** 给定相似度阈值 0.3，且候选题目的相似度为 0.2
- **THEN** 系统不应将该题目包含在检索结果中

#### Scenario: 无相似题目时返回空列表
- **WHEN** 给定一个新题目，但历史库中没有任何题目与其标签重叠
- **THEN** 系统返回空的示例列表

### Requirement: 策略必须构建包含示例的 few-shot prompt

系统 SHALL 将检索到的相似题目及其解答构建成结构化的 prompt，包含示例题目描述、标签和解答代码。

#### Scenario: 构建单个示例的 prompt
- **WHEN** 检索到 1 个相似题目及其解答
- **THEN** prompt 包含该示例的题目标题、描述、标签列表和 Python 解答代码

#### Scenario: 构建多个示例的 prompt
- **WHEN** 检索到 3 个相似题目
- **THEN** prompt 按相似度从高到低顺序包含所有 3 个示例

#### Scenario: 无示例时使用基础 prompt
- **WHEN** 没有检索到任何相似题目
- **THEN** 系统使用不包含示例的基础 prompt

### Requirement: 策略必须支持可配置的检索参数

系统 SHALL 允许用户配置示例数量、相似度阈值和相似度计算方式。

#### Scenario: 配置示例数量
- **WHEN** 用户配置 num_examples=5
- **THEN** 系统最多返回 5 个相似题目作为示例

#### Scenario: 配置相似度阈值
- **WHEN** 用户配置 min_similarity_score=0.5
- **THEN** 系统只返回相似度 >= 0.5 的题目

#### Scenario: 使用默认配置
- **WHEN** 用户未提供配置参数
- **THEN** 系统使用默认值：num_examples=3, min_similarity_score=0.3, similarity_metric="tag_overlap"

### Requirement: 策略必须从历史评估结果加载示例库

系统 SHALL 从项目的评估结果中加载已成功求解的题目及其解答作为示例库。

#### Scenario: 加载成功解答
- **WHEN** 历史结果中存在状态为 success 且通过所有测试的题目
- **THEN** 系统将该题目及其代码加入示例库

#### Scenario: 过滤失败解答
- **WHEN** 历史结果中存在状态为 failed 的题目
- **THEN** 系统不应将该题目加入示例库

#### Scenario: 示例库为空时正常降级
- **WHEN** 没有任何历史评估结果可用
- **THEN** 策略正常执行但不使用示例（等同于 Vanilla 策略）

### Requirement: 策略必须与现有策略接口兼容

系统 SHALL 继承 StrategyBase 并实现标准的 execute 方法，返回 ExecutionResult。

#### Scenario: 执行成功返回结果
- **WHEN** 策略成功生成代码
- **THEN** 返回包含代码、token 消耗和执行状态的 ExecutionResult

#### Scenario: 执行失败记录错误
- **WHEN** LLM 调用失败或代码生成失败
- **THEN** ExecutionResult 的 status 标记为 failed 并包含错误信息

#### Scenario: 策略可在 harness 中注册和调用
- **WHEN** 策略注册到 STRATEGY_MAP
- **THEN** 用户可通过 --strategy few_shot_learning 参数调用该策略
