# Tasks: recommendation-enhancements

## Task 1: 梯度排序、成本估算与提升维度

**文件**: `src/recommender.py`、`tests/test_recommender.py`

- [x] 输出按难度梯度稳定排序（easy→medium→hard，无难度最后）
- [x] 成本估算：记录结算助手、题级/难度级回退、单题与总估算字段
- [x] `expected_improvement_dimensions` 与报告级 `covered_dimensions`
- [x] 单元/集成测试：梯度顺序、成本回退链手算对账、维度提取

## Task 2: 文档与回归

**文件**: `README.md`

- [x] 推荐章节补梯度、成本估算与维度说明
- [x] 全量测试 + `openspec validate` 通过
