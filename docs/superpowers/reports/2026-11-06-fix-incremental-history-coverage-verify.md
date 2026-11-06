# 增量评估历史覆盖验证

变更 `fix-incremental-history-coverage`，实现提交 `94be7d8`，对应 GitHub Issue #362。

## 结论

通过。OpenSpec 任务 1/1 完成，增量规格的 3 个场景均有 CLI 测试证据。

- 历史完整时只执行变化题并按完整结果重算报告。端到端测试覆盖常规策略与按难度选策略的 `cost_aware` 汇总结果。
- 历史缺失或损坏时执行全量评估。测试覆盖结果文件全部丢失、索引损坏和结果 JSON 损坏。
- 新增策略、缺少当前策略文件、未变题缺记录或记录重复时，CLI 回退全量评估。测试核对每个当前策略的 summary 分母和成功率，校验结果文件每题恰好一条，并确认新历史指向完整结果目录。
- 缩减策略后可继续复用完整历史，已移除策略不进入当前报告。仅删题时执行全量评估。

## 执行证据

- `python3 -m pytest -q --no-cov tests/test_incremental_e2e.py tests/test_incremental_history.py tests/test_detector.py tests/test_fingerprint.py tests/test_merger.py tests/test_merger_integration.py` 通过 65 项，有两条既有测试收集或依赖弃用告警。新增回归在修复前分别观察到 1、1、2、4 道题，预期均为 3 道。
- `python3 -m pip wheel --no-build-isolation --no-deps --wheel-dir "$(mktemp -d)" .` 成功构建 wheel。
- `comet classic openspec -- validate fix-incremental-history-coverage --strict`、两处 Python 文件的 Ruff 格式与 lint 检查、Git 空白检查均通过。

## 实现与规范一致性

`src/main.py:2075` 在更改题目筛选和输出增量提示前检查历史 ID 与记录数。覆盖缺失时，完整题集沿用同一评估与历史保存路径。变更遵循 tweak 的精简 `design.md`。配置为 `review_mode: off`，本次验证直接核对了提交 diff、端到端场景与规范。
