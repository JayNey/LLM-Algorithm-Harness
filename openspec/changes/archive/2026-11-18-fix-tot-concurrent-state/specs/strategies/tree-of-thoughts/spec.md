## ADDED Requirements

### Requirement: 并行搜索状态隔离
共享同一 ToT runtime 的多题执行 MUST 独立保存每次搜索的调用轨迹、响应、调用上下文和预算停止原因。每次已发生调用 MUST 仅归属当前题，既有串行行为、选中代码、隐藏判题和持久化结果 MUST 保持一致。

#### Scenario: 两题交错执行
- **WHEN** Harness task-service 的两个 worker 通过同一 runtime 并行执行各含一次生成和一次评分的题目
- **THEN** 各题仅含本题提示和响应的两条迭代，token 和费用分别正确，总量不丢失不重复，保存的结果保持同一归属

#### Scenario: 异常与预算停止隔离
- **WHEN** 一个题目模型异常或预算拒绝，而另一题仍在同一 runtime 执行
- **THEN** 异常或预算停止仅影响所属题，另一题保留正确轨迹、用量和终态，后续串行调用亦不继承这些状态
