# Proposal: 基于模型表现的难度自动重标注（issue #82）

## Why

题库难度标注来自来源站点（如 LeetCode），与实际 LLM 表现经常不符：标记 easy 的题目通过率可能低于 30%。issue #82 要求基于历史评估数据自动重新标注难度，为难度分层的成本控制（#85）与策略映射（#56b）提供更可靠的输入。

## What Changes

- 新增 `src/difficulty_calibration.py`：从历史评估产物（`*_results.json`）按题目聚合成功率与平均迭代次数，按可配置阈值重标注难度（默认 >70% → easy、30–70% → medium、<30% → hard）。
- 新增 CLI：`harness recalibrate --history results/ --output data/calibrated.json [--dataset data/problems.json] [--easy-threshold 0.7] [--hard-threshold 0.3] [--report PATH]`，输出重标注后的完整题库 JSON 与难度变更报告（前后分布对比、逐题变更明细、无历史数据题目清单）。
- 无历史记录的题目保留原标注并在报告中列出；判定口径与推荐器一致（status=success 且隐藏测试通过才算通过）。
- CLI 采用顶层扁平命令 `harness recalibrate`（issue 文案中的 `problems recalibrate` 嵌套为建议形式，按仓库既有扁平 CLI 惯例实现）。

## Capabilities

### New Capabilities

- `difficulty-calibration`: 基于历史评估数据的难度重标注行为与验收要求。

### Modified Capabilities

（无——只读消费历史产物与题库，不改变评估执行流程）

## Impact

- 代码：新增 `src/difficulty_calibration.py`；`src/main.py` 新增 `recalibrate` 子命令；新增 `tests/test_difficulty_calibration.py`；README 更新。
- 兼容性：独立分析命令，不触碰 run/experiment/import 路径；输出为新文件，不覆盖原题库。
