# evaluation-results-api 验证报告

结论：PASS

## 范围

- change：`evaluation-results-api`
- 分支：`comet/evaluation-results-api`
- 验证模式：full。`comet state scale` 统计任务数超过 3、变更文件数超过 8，结果为 full。
- 基线：`ddcb7ade01c2a4205c94a3331c4ccefc46c17fbe`
- 代码审查：`review_mode` 为 `standard`。集成审查覆盖最终实现；审查发现的 PostgreSQL 标签 SQL 已修，随后的任务审查通过，Critical 0，Important 0。

## 完整性

`openspec/changes/evaluation-results-api/tasks.md` 的 10 项全部为 `[x]`。计划任务 1 到 11 也已勾选。OpenSpec 校验通过。

| 规格场景 | 证据 |
| --- | --- |
| 按运行标识读取本人的任务结果 | `GET /api/v1/results/{run_id}` 先匹配本人 `evaluations.id`，再匹配 `run_id`。`tests/test_api_evaluation_results.py::test_results_api_hides_other_users_and_paginates_problems` |
| 详情分页不截断策略汇总 | 同一测试断言缩小 `limit` 后策略汇总仍覆盖全部单元并含 `avg_execution_time` |
| 他人运行不可见 | 他人 id 与 `run_id` 都是 404，列表不返回该运行 |
| 按标签过滤结果列表 | `test_tag_filter_matches_exact_case_on_list_and_success_rate`：`Graph` 命中，`graph` 不命中；列表与成功率使用同一规则 |
| 成功与失败混合时的成功率为 0.75 | `test_analytics_match_stored_rows` |
| 未知成本不计入美元合计 | 同一测试：合计 0.2，未知数量为 1 |
| 缺少迭代次数字段 | 同一测试：缺失键计入未知，不显示为 0 |
| 多轮策略记下迭代次数 | `tests/test_evaluation_result_iterations.py`：2 轮轨迹写入 `metrics.iterations == 2` |
| 策略对比与详情一致 | `test_compare_matches_detail_and_empty_history` |
| 没有历史时返回空序列 | 同一测试 |
| 雷达维度与题目数 | `test_radar_and_empty_learning_curve`；未映射标签 `hash-table` 仍返回七个维度且分数为 0 |
| 空学习曲线 | 同一测试返回 200 和空序列 |
| 按已保存的失败模式汇总 | `test_failure_summary_keeps_stored_mode` |
| 失败案例只包含失败单元 | 同一测试 |
| CSV 缺失字段留空 | `test_reports_match_json_and_blank_missing_csv_fields` |
| Markdown 与 JSON 的成功率相同 | 同一测试 |
| 他人运行不能导出 | 他人 CSV 为 404，且无文件正文 |
| 已知成本在混合未知成本时仍显示 | `test_markdown_keeps_known_cost_when_another_unit_is_unknown` |

## 正确性

- 成功以 `status == "success"` 计数。成本跳过 `cost_unknown`。迭代只聚合存在的 `metrics.iterations`。
- 详情、对比、图表和报告摘要共用 `aggregate`。难度优先 `metrics.difficulty`，缺失时用 `problems.difficulty`。
- 标签是解码后的精确、区分大小写成员。SQLite 使用 `json_each`。PostgreSQL 使用绑定参数的 `CAST(column AS jsonb) @> jsonb_build_array(...)`，不再把 `json_array_elements` 放进没有 `LATERAL` 的 `FROM`。
- 降序为 `NULLS LAST`，升序为 `NULLS FIRST`。
- A/B 对比调用现有 `ABTestService.results`。学习曲线读取该用户已完成的 `benchmark_runs`。既有按套件的学习曲线端点未改。
- 失败汇总只数已保存的 `failure_mode` / `failure_category`，聚类只调用 `normalize_message`。
- proposal 的目标已满足：查询、统计、对比、可视化数据、失败分析和报告导出都从已落库结果读取。

## 一致性

- 高层设计 `openspec/changes/evaluation-results-api/design.md` 与 Design Doc `docs/superpowers/specs/2026-10-17-evaluation-results-api-design.md` 都要求读已落库结果、共用一套聚合、不新建表、不把 Redis 当作正确性依赖、雷达使用 `capability_profiler`。实现遵循这些决定。
- delta spec 与 Design Doc 无矛盾。Build 没有改规格条文。
- 两处保持设计约束，不作为失败项：CSV 由本服务按列名书写，不调用 `CSVExporter.export`，因此写入已保存的 `error_message`，不做生成器那层脱敏。HTML 图仍调用未修改的 `ChartGenerator`；摘要里的成本是已落库合计，占位迭代没有 token 拆分时，token 图的成本轴沿用生成器自己的估算。

## 安全

- 未登录走现有认证错误。路径和列表都限制在当前用户。他人资源与不存在资源同为 404。
- 标签进入绑定参数，不拼进 SQL。排序列是白名单。
- 新代码没有硬编码密钥。报告不回放生成代码或沙箱轨迹。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `MPLCONFIGDIR=/tmp/mpl-cache python3 -m pytest tests/test_api_evaluation_results.py tests/test_evaluation_result_iterations.py tests/test_evaluation_results_service.py -q --no-cov --tb=line` | 16 passed，退出码 0 |
| `comet classic openspec -- validate evaluation-results-api --strict --type change` | Change is valid，退出码 0 |

PostgreSQL 标签 SQL 和空值排序由方言编译测试锁定，本环境没有连接真实 PostgreSQL。
