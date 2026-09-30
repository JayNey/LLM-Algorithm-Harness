# Design: 推荐系统增强

## 实现说明

- **难度梯度排序**：`_recommend` 在选出 top-N（相关度排序不变）后，输出按 `DIFFICULTY_RANK = {easy: 0, medium: 1, hard: 2}` 升序稳定排序；同难度内保持相关度顺序。未标注难度的题排最后。
- **成本估算**：本地结算助手 `_record_cost(record)`（与 cost_strategy.result_cost 同口径：`pricing_metadata.total_cost` 且 `usage_known != False` 且 `pricing_known != False`、有限非负计入，否则该记录计 unknown；对 dict 记录直接结算，模块独立、不依赖 #85 分支代码，合并后可归并）。估算层级：该题历史记录的已知成本均值 → 同难度均值 → 未知（`None`）。报告新增 `estimated_cost_usd`（单题）与 `total_estimated_cost_usd`（已知部分合计 + unknown 题数）。
- **预期提升维度**：`expected_improvement_dimensions` = 该题匹配的弱项分组中的标签维度（`tag:*` 组的去 tag 名，含 tag_combination 的逗号组合）；报告级 `covered_dimensions` 为全部推荐覆盖维度的并集。

## 边界

- 成本估算是历史均值启发式，不预测未来计价变化；未知成本如实标注，不按默认单价折算。
- 相关度入选逻辑（弱项匹配 + 失败率排序 + limit 截断）不变，梯度只影响输出顺序。
