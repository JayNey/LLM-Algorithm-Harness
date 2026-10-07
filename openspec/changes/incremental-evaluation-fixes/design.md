# Design: 增量评估修复

## 三个缺陷与修法

### 缺陷 1：problem_ids 过滤不被支持（选集崩溃）

`main.py` 设 `config.problem_filters["problem_ids"] = list(changed_ids)`，随后 `_load_problems` 以 `filter_problems(problems, **filters)` 展开 → `TypeError`。

修法：`ProblemLoader.filter_problems` 新增 `problem_ids: list[str] | None = None` 参数（在 difficulty/tags/limit 过滤之前按 id 白名单过滤）。签名扩展向后兼容。

### 缺陷 2：历史结果文件形状不匹配

`update_incremental_history` 记录的 `result_path` 是 `<run>/summary.json`（`{strategy: StrategyReport-dict}`），而 `load_historical_results` 期望 `{strategy: [result_dict, ...]}`。对 summary 的 items 遍历拿到的是 report dict 的键（字符串），`result_data.get(...)` 抛 `AttributeError`（不在 except 元组内）→ 回退。

修法：
- RunRecord 记录 **run 目录**（`result_path` 语义改为目录）；`load_historical_results` 改为在目录内读取 `*_results.json`（`vanilla_results.json` 等，形状天然匹配），合并各策略文件。
- `main.py` 传 `str(run_path)`（run 目录）而非 summary.json；`update_incremental_history` 的 `run_id` 推导相应修正。

### 缺陷 3：合并报告硬编码

`merged_reports` 直接 new `StrategyReport(estimated_cost_usd=0.0, avg_attempts_per_problem=1.0, ...)`。修法：从合并后的结果列表真实重算——total/solved/failed/success_rate/avg_attempts（sum(iterations)/total）/total_tokens/avg_tokens/estimated_cost（经 llm_traces 定价口径，复用 `_estimate_cost` 思路）/by_difficulty（复用 harness 的 `_calculate_by_difficulty`，静态调用）。`formal_*` 字段按结果里的 `formal_evaluable`/`hidden_result` 统计。

### 兜底语义保持

三处兜底（无匹配 run / 变化过大 / 集成异常）全部保留：任何失败都回退全量评估，只是修复后正常路径应真正生效，且回退时有明确日志。

## 测试策略

- 单元：`filter_problems(problem_ids=...)` 白名单过滤。
- 端到端（mock LLM，进程内 `_run_main`）：首跑 3 题（生成 `.incremental/history.json` 与 run 目录）→ 修改 1 题、新增 1 题 → 第二跑断言：仅 2 题执行、历史结果复用（source=reused）、合并报告 total=4、成本非零、难度分布存在。历史文件损坏/无匹配 run 的回退分支各一。
