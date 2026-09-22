## Purpose

Self-Consistency 策略通过并行生成多个候选解并投票选择最佳答案，提升算法问题求解的准确率。

## ADDED Requirements

### Requirement: 策略可配置候选数量

系统 SHALL 允许配置生成的候选解数量，默认值为 5。

#### Scenario: 使用默认候选数量
- **WHEN** 策略配置未指定候选数量
- **THEN** 系统生成 5 个候选解

#### Scenario: 使用自定义候选数量
- **WHEN** 策略配置指定候选数量为 3
- **THEN** 系统生成 3 个候选解

### Requirement: 生成多个不同候选解

系统 SHALL 使用较高温度参数（默认 0.8）生成多个候选解，以增加多样性。

#### Scenario: 生成多样化候选解
- **WHEN** 策略执行并生成 5 个候选解
- **THEN** 每个候选解使用 temperature=0.8 生成
- **THEN** 候选解之间应具有差异性

### Requirement: 测试所有候选解

系统 SHALL 对每个生成的候选解执行沙箱测试，验证其正确性。

#### Scenario: 测试通过的候选解
- **WHEN** 候选解代码通过所有公开测试用例
- **THEN** 该候选解标记为通过

#### Scenario: 测试失败的候选解
- **WHEN** 候选解代码未通过测试用例
- **THEN** 该候选解标记为失败但不影响其他候选解

### Requirement: 投票选择最佳答案

系统 SHALL 统计所有通过测试的候选解，按代码字符串完全匹配分组计数，选择出现频率最高的代码作为最终结果。

#### Scenario: 多数候选解相同
- **WHEN** 5 个候选解中有 3 个代码相同且都通过测试
- **THEN** 选择该代码作为最终结果
- **THEN** 标记执行成功

#### Scenario: 所有候选解不同
- **WHEN** 所有通过测试的候选解代码都不同
- **THEN** 选择第一个通过测试的候选解
- **THEN** 标记执行成功

#### Scenario: 无候选解通过测试
- **WHEN** 所有候选解都未通过测试
- **THEN** 标记执行失败

### Requirement: 记录详细执行信息

系统 SHALL 记录每个候选解的生成过程、代码、测试结果和投票统计信息。

#### Scenario: 记录候选解详情
- **WHEN** 策略执行完成
- **THEN** ExecutionResult 包含所有候选解的 IterationResult
- **THEN** 每个 IterationResult 包含 LLM 响应、提取的代码和沙箱测试结果

#### Scenario: 记录投票统计
- **WHEN** 策略执行完成且有多个候选解通过测试
- **THEN** ExecutionResult 包含投票统计信息（每个代码的出现次数）
