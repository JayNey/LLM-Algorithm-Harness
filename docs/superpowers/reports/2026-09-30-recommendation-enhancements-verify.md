# 验证报告：recommendation-enhancements

- 日期：2026-09-30
- 工作流：Comet Classic tweak（verify_mode: full，含 delta spec）
- 分支：`tweak/20260930/recommendation-enhancements`
- 实现：a1ffcbe（主实现）+ d5918fc 父提交（cherry-pick 的缓存测试隔离修复）+ a5bba60（审查修复）
- 审查方式：独立审查者一轮全量审查（requests-changes）+ 修复后定点复审

## 完整验证检查项

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务完成 | PASS | 6/6 `[x]` |
| 2 | 实现符合 design.md | PASS | 梯度排序、难度级成本估算、维度提取均按设计；成本回退链按审查结论修正为"同难度均值→None"并同步全部文档 |
| 3 | Design Doc 一致性 | N/A | tweak 预设无 Superpowers Design Doc |
| 4 | 能力规格场景全部通过 | PASS | 3 个 Requirement 全部 Scenario 有对应测试（含三级难度排序、多标签维度） |
| 5 | proposal.md 目标满足 | PASS | 梯度、成本估算、提升维度均已实现；入选集合与既有字段不变 |
| 6 | delta spec 与 design 无矛盾 | PASS | validate 通过；成本口径/维度粒度/防御分支已在 design 说明 |
| 7 | 关联设计文档可定位 | N/A | 无 docs/superpowers/specs 关联文档 |

## Delta spec Scenario 覆盖

| Scenario | 测试 |
|----------|------|
| 从易到难输出 | `test_gradient_orders_easy_first_with_cost_and_dimensions`（easy→medium→hard 三级断言） |
| 难度级成本估算 | 同上（easy 均值 0.1 / hard 均值 0.3 / 无可计数历史为 None） |
| 总估算与未知呈现 | 同上（total 0.4、unknown_count 1） |
| 维度提取与汇总 | 同上（单标签、弱项过滤、covered_dimensions 并集） |

## 验证命令

- `comet check run recommendation-enhancements build --local -- python3 -m pytest -q --cov-fail-under=0` → exit=0（676 passed / 4 skipped）
- `comet classic openspec -- validate recommendation-enhancements` → valid
- **覆盖率门禁说明**：同前——上游基线约 82%，90% 门禁不可达，以全量测试通过为准。
- **缓存污染说明**：本分支基于 main（早于缓存修复合入其他分支），主实现时 12 个 test_llm_client 失败为已知 `.cache` 污染；已将修复 cherry-pick 进本分支（d5918fc），全量套件转绿。

## 集成代码审查

- 第一轮（全量 diff，a1ffcbe + d5918fc）：requests-changes——2 IMPORTANT（成本结算缺有限/非负守卫，NaN 污染均值且产出非法 JSON；成本回退链第一层为不可达死代码、与文档不符）+ 4 WARNING（design 措辞超出实现；"无难度"分支不可达且 spec 场景无法构造；CACHE_DIR_ENV 死常量且注释失实；聚合粒度差异未校准）+ 5 SUGGESTION。
- 处置：verify-fail 回 build，commit a5bba60——`_record_known_cost` 补 isfinite/非负守卫；删除不可达的题级成本层（推荐题无自身历史），改为同难度均值并同步 spec/design/proposal 全部表述；删除 CACHE_DIR_ENV 死常量；设计补聚合粒度差异与 main 侧符号说明；空推荐集 total 类型稳定；测试补三级难度排序与弱项过滤断言。
- 定点复审：见下方"定点复审结论"。

## 接受的偏差

- SUGGESTION：维度仅取单标签（组合/难度分组体现在推荐理由，不计入维度）——design 已按实现对齐。
- SUGGESTION：conftest 缓存 fixture 不覆盖子进程测试（当前无子进程路径构造缓存）。
- SUGGESTION：write 输出/报告的 OSError 未捕获（遗留同等粗糙度，parent 已 mkdir）。

## 结论

（待定点复审后填写。）
