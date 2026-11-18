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

#### Scenario: 检索控制参数与模型生成参数分离
- **WHEN** 用户同时配置 num_examples、similarity_metric、min_similarity_score、example_source 和合法的模型生成扩展
- **THEN** 检索配置仍实际生效，模型请求只包含生成参数，内部控制键不进入 SDK 或 HTTP 请求
- **AND** 合法扩展保持原有覆盖优先级并参与缓存键，控制参数本身不改变相同 prompt 的模型缓存键

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

### Requirement: 历史示例必须排除目标题及可识别重复题

系统 MUST 在检索及提示构建时排除与目标具有相同题目 ID、相同非空平台与来源题号、相同规范化来源 URL 或相同规范化题面的示例。排除 MUST 独立于相似度阈值。规范化题面只合并空白和大小写，不推断语义改写或仅标题相同的题目。

#### Scenario: 历史已有目标答案
- **WHEN** 历史存在目标 ID 的成功答案，且 min_similarity_score 为 0
- **THEN** 检索与最终提示均不包含该答案，其他不同题的相似示例仍可使用

#### Scenario: 来源别名及来源版本变化
- **WHEN** 示例与目标 ID 不同，但平台与来源题号相同，或来源 URL 规范化后相同
- **THEN** 示例被排除，即使来源数据版本不同

#### Scenario: 没有来源身份的重复题
- **WHEN** 示例与目标 ID 不同且来源身份缺失，但题面仅有空白或大小写差异
- **THEN** 示例被排除；题面不同且仅标题相同不会被据此排除

#### Scenario: 调用者直接传入目标示例
- **WHEN** 提示构建收到绕过检索的目标历史答案
- **THEN** 提示构建再次过滤该答案，过滤后为空则返回基础提示

### Requirement: 历史加载必须校验题目快照与成功资格

历史示例 MUST 携带可读取的题目 ID、标题、描述、标签列表及来源字段。系统 SHALL 优先读取版本化题目快照，并兼容信息完整的旧顶层字段及 problem_metadata。缺少必要题意、损坏或未知版本的记录 MUST 明确告警并跳过，不编造示例题意。未完成、失败或具有失败测试的答案 MUST 不作为成功示例。

#### Scenario: 正常策略结果写出后复用
- **WHEN** 正常策略执行成功并通过标准结果写出，再由历史示例加载器读取
- **THEN** 不需要手工补元数据，即可检索到标签相似的不同题，提示包含原题意与其对应代码

#### Scenario: 旧格式与损坏记录混合
- **WHEN** 历史同时存在完整旧字段、缺少元数据、未知快照版本、损坏 JSON 或损坏单条记录
- **THEN** 完整旧记录可用，其他记录按原因告警并跳过，有效示例仍能加载

#### Scenario: 所有示例不可用
- **WHEN** 没有通过校验且与目标不同的示例
- **THEN** 策略使用基础提示并安全执行

### Requirement: 示例集合与选中来源必须可追溯

系统 SHALL 为加载的示例集合记录契约版本、稳定内容摘要及历史来源，并在 Few-Shot 结果记录集合身份、选中示例身份与重叠排除信息。相同有效内容与排序规则 SHALL 产生相同身份，题意、标签、来源身份或代码变化 MUST 改变集合身份。Few-Shot SHALL 继续遵守禁用增量结果复用的兼容规则。

#### Scenario: 集合身份反映实际内容
- **WHEN** 相同历史记录以不同扫描顺序加载，或其中的代码随后变化
- **THEN** 扫描顺序不改变集合身份，代码变化产生不同身份

#### Scenario: 来源与重叠审计
- **WHEN** 策略选中相似题并排除目标别名
- **THEN** 结果可追溯到示例历史文件及记录身份，且记录排除的身份与原因

#### Scenario: 不复用 Few-Shot 增量结果
- **WHEN** Few-Shot 运行请求增量结果复用
- **THEN** 仍执行完整评测，恢复已有不兼容复用计划时明确拒绝
