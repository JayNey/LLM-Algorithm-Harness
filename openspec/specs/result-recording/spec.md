# result-recording Specification

## Purpose
确保每个题目×策略组合都有可追溯的终态结果：失败结果与原因可查，修复反馈保留完整题面，每轮交互轨迹与用量可审计，汇总口径可对账。

## Requirements

### Requirement: 失败结果终态保留
系统 MUST 在策略正常结束或异常终止时，为每个被请求执行的题目×策略组合生成终态 `ExecutionResult`，并保留最后一次有效沙箱结果及其失败用例明细。

#### Scenario: 连续多轮全部失败
- **WHEN** 多轮策略所有轮次都未通过测试
- **THEN** `final_result` 与失败用例仍可查看，失败原因为 `wrong_answer`

#### Scenario: 中途模型调用失败
- **WHEN** 多轮策略在后续轮次遇到模型 API 报错
- **THEN** 已完成轮次的轨迹保留，该题目仍出现在最终报告而不是被丢弃

#### Scenario: 策略执行抛出未捕获异常
- **WHEN** Harness 捕获策略执行异常
- **THEN** 为该题目合成 `system_error` 终态记录并计入结果列表

### Requirement: 失败原因分类与对账
系统 SHALL 为失败结果标记 `wrong_answer`、`code_extraction_failed`、`model_error`、`system_error` 分类，汇总与策略对比使用同一分母口径并单独统计系统失败与模型失败。

#### Scenario: 报告计数对账
- **WHEN** 生成策略报告
- **THEN** 总数等于成功数与各类失败数之和

#### Scenario: 策略对比口径一致
- **WHEN** 调用 `compare_strategies`
- **THEN** 各策略分母与对应报告的总数口径一致

### Requirement: 反馈上下文完整
多轮修复提示 MUST 包含完整题意与约束，反馈内容仅来自本轮沙箱执行产生的可见失败信息。

#### Scenario: 后续轮次提示
- **WHEN** 构建第二轮及之后的修复提示
- **THEN** 提示包含题意与约束，反馈仅包含沙箱可见失败输入与具体错误

### Requirement: 每轮轨迹与用量记录
系统 MUST 保存每轮脱敏后的请求、原始文本响应、提取代码、每轮测试摘要与 token/耗时数据；供应商 usage 缺失时显式标记。

#### Scenario: usage 缺失
- **WHEN** 供应商响应不包含 usage 数据
- **THEN** 该轮记录 `usage_missing` 标记且不抛出异常

#### Scenario: 轨迹脱敏
- **WHEN** 保存的请求或响应文本包含凭证形态内容
- **THEN** 轨迹中的敏感内容已被脱敏

### Requirement: 执行耗时实测
`execution_time_seconds` MUST 反映实际测量值。

#### Scenario: 策略完成计时
- **WHEN** 策略执行完成
- **THEN** `execution_time_seconds` 为实际测量的非零耗时
