# Proposal: 修复增量评估使其真正生效（issue #87 后续）

## Why

增量评估已由 PR #122 交付（issue #87 已关闭），但审计发现主流程集成存在三个缺陷，导致**增量模式从未真正生效**——每次都在"只评估变化题目"的选集阶段或历史结果加载阶段抛错，被外层兜底捕获后静默回退全量评估：

1. **选集崩溃**：集成通过 `config.problem_filters["problem_ids"]` 把变化题目传给 `ProblemLoader.filter_problems`，但该方法只支持 `difficulty/tags/limit`，展开 `**filters` 时抛 `TypeError`。
2. **历史结果加载必然失败**：`result_path` 指向 `summary.json`（形状为 `{strategy: StrategyReport-dict}`），而 `load_historical_results` 期望 `{strategy: [result_dict, ...]}`；对 summary 遍历时抛 `AttributeError`，不在捕获列表内，直接触发回退。
3. **合并报告丢数据**：合并后的报告 `estimated_cost_usd=0.0`、`avg_attempts_per_problem=1.0` 硬编码，且缺 `pricing_metadata`/`by_difficulty` 等字段，后续 `print_report`/`save_results` 展示的成本与难度分布失真。

由于回退是静默的（仅 warning 日志），用户以为增量在跑，实际每次都是全量重跑。

## What Changes

- `ProblemLoader.filter_problems` 新增 `problem_ids: list[str] | None` 参数（与现有 difficulty/tags/limit 并存）。
- 历史结果加载改用 per-strategy 结果文件（`<strategy>_results.json`，形状已匹配 `[result_dict, ...]`）：RunRecord 记录 run 目录，加载时定位目录内的 `*_results.json`。
- 合并报告改为从合并后的结果**真实重算**全部指标（成本按 llm_traces 定价口径、难度分布、formal 指标），不再硬编码。
- 新增端到端测试证明闭环：首跑全量 → 数据集改动一题 → 第二跑只评估变化题并复用历史结果 → 合并报告完整。

## Capabilities

### New Capabilities

- `incremental-evaluation`: 增量评估的触发条件、选集、历史结果复用与合并报告的验收要求。

### Modified Capabilities

（无——PR #122 未留下增量相关 spec）

## Impact

- 代码：`src/problem_loader.py`、`src/main.py`、`src/incremental/detector.py`、`src/incremental/merger.py`；新增 `tests/test_incremental_e2e.py`。
- 兼容性：`filter_problems` 新参数带默认值；summary.json 产物结构不变；非增量路径不受影响。
