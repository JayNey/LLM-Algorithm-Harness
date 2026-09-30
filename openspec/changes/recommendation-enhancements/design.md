# Design: 推荐系统增强

## 实现说明

- **难度梯度排序**：`_recommend` 在选出 top-N（相关度排序不变）后，输出按 `DIFFICULTY_RANK = {easy: 0, medium: 1, hard: 2}` 升序稳定排序；同难度内保持相关度顺序。`Problem.difficulty` 为必填三值 Literal，"无难度"分支（rank 默认 3）仅为防御性代码。
- **成本估算**：本地结算助手 `_record_known_cost(record)`（与预算/成本模块同口径：`pricing_metadata.total_cost` 且 `usage_known != False` 且 `pricing_known != False`、有限非负计入，否则整条记录不可计数；无 llm_traces 的记录同样不可计数）。估算层级：推荐题均为未评估题、无自身历史，故直接取**同难度均值** → 无数据为 `None`。报告新增 `estimated_cost_usd`（单题）与 `total_estimated_cost_usd`（已知部分合计 + unknown 题数）。粒度差异说明：main 侧对应符号为 `RunCostMonitor.add_result`（混合 trace 会部分入账），本模块对任一 trace 不可计数即丢弃整条记录，归并时需校准该差异。
- **预期提升维度**：`expected_improvement_dimensions` = 该题匹配的弱项分组中的单标签维度（仅 `tag:*` 组的去 tag 名；标签组合与难度分组不计入维度，只体现在推荐理由）。报告级 `covered_dimensions` 为全部推荐覆盖维度的并集。

## 边界

- 成本估算是历史均值启发式，不预测未来计价变化；未知成本如实标注，不按默认单价折算。
- 相关度入选逻辑（弱项匹配 + 失败率排序 + limit 截断）不变，梯度只影响输出顺序。
