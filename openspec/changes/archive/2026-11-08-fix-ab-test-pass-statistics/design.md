## Context

详情页从结果 API 读取两组通过率，API 从 A/B JSON 产物读取数据。旧版 1.0 产物已保留逐题样本、正式和正式可评估标志。

## Decisions

- 使用同一聚合逻辑生成新报告并在 API 读取 1.0 报告时重算。结果标为 1.1。历史产物保留原样，离线阅读时可用 JSON 的版本区分口径。无法从逐题记录恢复的 1.0 报告由 API 提示重新运行。
- 样本口径读取每题的 `sample_passed`。正式口径在 `formal_evaluable` 的题目中读取 `formal_passed`。沿用评估报告对正式可评估但未通过的记录的计数规则。
- 保留 `comparison.statistics` 作为样本检验供现有调用方读取，在 `comparison.formal_statistics` 提供独立的正式检验。两组各用自己的二元向量计算通过率、区间和检验。
- 二元向量缺组或合并后仅有单一结果时返回不可检验。Welch t 检验还需要每个变体至少两条记录且至少一个变体内部存在变异。Markdown 标明两种检验和产物版本。
