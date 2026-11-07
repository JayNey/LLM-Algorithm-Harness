# 练习历史有效评测验证

对应 GitHub issue #366 与 `filter-incomplete-practice-history`。实现提交为 `d96a5153`。

## 规范覆盖

- 唯一实现任务已勾选。`result-recording` 中新增的有效评测要求覆盖两种历史场景，OpenSpec 严格校验通过。
- `test_analyze_returns_no_weaknesses_when_all_history_was_skipped` 验证原始记录条数为 1、已评测题数为 0、弱项和推荐为空。`test_preserves_difficulty_with_only_unexecuted_history` 验证原标签保留且 `has_data=false`。
- `test_analyze_excludes_skipped_records_from_weaknesses_and_practice` 验证混合历史中仅 3 条有效记录进入统计，真实答错和隐藏失败共计 2 条，仅有跳过记录的题目仍可被推荐。
- `test_aggregates_only_completed_evaluations` 验证校准使用同一分母和成功口径，成功率为 1/3，平均迭代次数为 2。

## 设计核对

- 推荐与校准在聚合前调用 `src/evaluation_history.py` 的共同判定。旧记录缺少完成标志时按终态统计，预算、不支持、取消及明确未完成的记录在进入统计前排除。
- 推荐保留原始记录计数，练习成本与弱项基于有效记录。无有效记录时沿用现有报告字段，无数据的难度判定保留题目标签。
- 实现和测试共 5 个文件，其他变更均为 OpenSpec 和 Comet 产物。实现符合精简设计，验证以本 change 的 `design.md` 为准。
- 最终 diff 已核对正确性、边界与安全。Tweak 状态为 `review_mode: off`，按配置跳过自动代码审查。

## 执行证据

- 修复前，4 个新增用例均因对应的未完成统计错误失败。修复后，推荐与校准的 25 个测试全部通过。
- Ruff 全仓检查、Black 对改动文件的检查、mypy 对 3 个改动源码文件的检查，以及 wheel 构建均通过。
- 首次全量运行受沙箱回环端口限制。允许回环后，4 个 Anthropic 用例因宿主安装了超出项目约束的 1.5.0 在 fixture 初始化时报错。使用 0.125.0 重跑该文件，12 个用例全部通过。
- 使用 Anthropic 0.125.0 的隔离源码快照执行 `python3 -m pytest -m 'not online'`，结果为 4045 通过、18 跳过，覆盖率 93.38%。唯一失败 `test_runner_executes_all_combinations_with_metadata` 需要 Git 元数据，快照中提交号为空。该用例在同一提交的实际分支、相同依赖配置下复测通过。跨两次运行，4046 个执行用例均有通过证据。

## 结论

本 change 的验收场景、构建和相关测试通过，具备归档条件。
