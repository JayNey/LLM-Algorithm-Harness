# Issue #494 验证报告

## 候选与范围

- 基线：`2d79bd95889c0305316bd989853cd43de2fcfe11`。
- A 防泄漏提交：`8ca1e2bd`；先加入六个真实失败回归，再修复并通过 47 项相关测试。
- B 历史复用与固定集合提交：`eafa98d4`。
- 源码 5 个、测试 5 个、用户文档 1 个，共 11 个交付文件；OpenSpec/Comet/本报告/变更说明为流程产物。范围与 Open 已批准提案一致，文件数授权见 `.comet/rulings.md`。
- 配置为 tweak 的 direct/direct/off。未派发独立 reviewer；本报告为当前会话验证，不冒充独立审查。

## 完整性、正确性与一致性

五项新增要求、18 个场景均有实现和离线行为证据；实现遵循先 A 后 B、统一快照、稳定集合身份、全题集重叠排除及恢复校验设计。

| 维度 | 结论 |
| --- | --- |
| 完整性 | 同一 tasks.md 的 11/11 项任务完成；5/5 项要求覆盖 |
| 正确性 | 18/18 个场景有实现及测试证据；必要验收全部通过 |
| 一致性 | 遵循已批准设计及 A→B 分别提交要求；无 CRITICAL、IMPORTANT 或待决行为偏差 |
| 独立审查 | 不适用：当前配置 review_mode=off；未宣称独立验收 |

| 要求与场景 | 实现 | 验证证据 |
| --- | --- | --- |
| 同 ID、同来源、同 URL、重复题面及阈值 0 排除 | `src/few_shot_examples.py:overlap_reason`、`src/strategies/few_shot_learning.py:retrieve_similar` | `test_historical_target_answers_never_enter_prompt` 四种身份；来源版本变化也不能绕过 |
| 绕过检索的提示构建及空示例降级 | `build_few_shot_prompt` 二次过滤 | `test_prompt_builder_filters_target_even_without_retrieval`、原有基础提示/空库测试 |
| 缺来源时的重复题面边界、仅同标题仍可用 | `overlap_reason` | `test_legacy_nested_metadata_and_missing_source_identity`；不同相似题使用同一标题的 A 回归 |
| 正常策略结果写出后直接加载、检索及正确题意/代码提示 | `ProblemSnapshot`、`StrategyBase.create_execution_result`、`load_history` | `test_real_result_write_load_retrieve_and_prompt`，真实 Harness、Vanilla、host 沙箱和标准 `save_results`，未手补快照 |
| 快照不携带反馈/隐藏测试、旧结果仍可读取 | `src/models.py:ProblemSnapshot` 与可选 `ExecutionResult.problem_snapshot` | 上述集成测试带真实反馈/隐藏用例，并校验快照字段及旧结果反序列化 |
| 完整旧字段/嵌套元数据兼容、损坏文件/单条及未知版本跳过 | `load_history` 逐条校验与告警 | `test_loader_isolates_invalid_rows_and_warns_for_missing_metadata`、`test_legacy_nested_metadata_and_missing_source_identity` 及原有加载测试 |
| 不使用未完成、公开失败或隐藏失败答案 | `_successful` | 上述混合历史测试覆盖三个失败来源 |
| 集合身份与来源追溯、输入变化改变摘要 | `create_manifest`、`example_reference` 与结果 `metadata.few_shot_examples` | `test_collection_identity_tracks_content_and_not_scan_order`、`test_collection_identity_includes_question_inputs`、真实写出集成测试 |
| 正式实验多组合固定集合、排除全部目标及后续历史污染 | `ExperimentRunner._prepare_few_shot_examples` | `test_all_combinations_share_frozen_examples`，串行/并行各覆盖两目标、两重复及运行中新增历史 |
| 实验恢复保留原集合与已完成组合 | 冻结文件、集合摘要、完整 manifest 校验与目标指纹 | `test_resume_keeps_original_collection_after_history_changes` |
| 集合丢失/篡改、旧格式缺证明、目标变化及实验元数据丢失拒绝恢复 | 同上，在组合调度前校验 | `test_resume_rejects_unverifiable_collection_before_model_calls` 五种损坏模式，原产物保留且无新增模型调用 |
| 非 Few-Shot 实验原规则不变 | 非 Few-Shot 提前返回 | 原有 `tests/test_experiment.py` 全部场景 |
| 阶段 3 增量复用兼容边界 | 继续沿用 `src/main.py:select_incremental_results` 的 Few-Shot 禁用规则 | `test_run_dependent_execution_evaluates_the_full_selection[examples]`、`test_few_shot_cannot_resume_an_incremental_reuse_plan` |
| 检索控制不进入供应商请求 | `StrategyBase._provider_custom_params` | `tests/test_strategy_provider_params.py` 在 OpenAI/local/Anthropic 真实 SDK 与离线 HTTP 边界校验新控制键 |

## 实际检查

运行目录均为 `/Users/verstappen/LLM-Algorithm-Harness`。Python 为 `/private/tmp/harness-review-env/bin/python`，版本 3.12.16；不调用在线模型。

| 检查 | 结果与证据 |
| --- | --- |
| A 回归 RED/GREEN | `/private/tmp/issue-494-a-red.log` 六个预期断言失败；`/private/tmp/issue-494-a-green.log` 47 passed |
| B 与实验 RED | `/private/tmp/issue-494-b-red.log` 三个预期失败；`/private/tmp/issue-494-experiment-red.log` 七个预期失败；实验元数据丢失额外回归见 `/private/tmp/issue-494-missing-metadata-red.log` |
| 最终必要验收 | `python -m pytest tests/test_few_shot_history.py tests/test_few_shot_experiment.py tests/test_few_shot_learning.py tests/test_strategy_provider_params.py tests/test_models.py tests/test_strategies.py tests/test_harness.py tests/test_experiment.py tests/test_incremental_e2e.py --no-cov -q`：278 passed，9 个既有模型收集/弃用警告；日志 `/private/tmp/issue-494-targeted-final.log` |
| 全仓 Ruff | `python -m ruff check .`：通过 |
| 类型检查 | `python -m mypy src/ --ignore-missing-imports --cache-dir /private/tmp/issue-494-mypy`：104 个源码文件通过；日志 `/private/tmp/issue-494-mypy-full.log` |
| 改动 Python 文件 Black | `black --check` 覆盖 10 个改动 Python 文件，通过；Black 临时安装在 `/private/tmp/issue-494-lint` |
| 文本编码 | `python scripts/find_missing_encoding.py`：Implicit text encodings: 0 |
| 格式及规格 | `git diff --check` 通过；`comet classic openspec -- validate fix-few-shot-history-leakage --strict` 通过 |

## 扩展检查与限制

- 全仓命令 `python -m pytest --no-cov -q` 实际尝试，收集 4384 项，在约 16% 处因已确认的沙箱本地端口限制停止，没有全仓通过结论；日志 `/private/tmp/issue-494-full-suite.log`。中断时 pytest 清理出现的 `KeyError` 属于本次中断回执，不作为产品通过证据。
- `tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http` 单独复现 `listener.bind((127.0.0.1, 0))` 的 `PermissionError`，日志 `/private/tmp/issue-494-loopback-repro.log`。
- 在允许回环端口的执行环境中复核 `test_full_model_ids_round_trip_over_http`、`test_full_model_id_auth_and_validation_over_http`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]` 和 `[ab]`，4 passed，日志 `/private/tmp/issue-494-loopback-green.log`。
- 扩展运行使真实历史结果可被加载后，原有“无示例”单测因读到仓库历史而失败；已将 Few-Shot 单测统一隔离到各自临时目录，最终 278 项验收覆盖该修复。没有删除用户历史文件。
- 不执行语义改写或跨语言题意判同，仅支持批准的 ID、来源和规范化相同题面边界。旧缺题意的结果仍可通用读取，但不能作为示例。
- 必要验收无失败；完整全仓测试、在线模型评测及独立 reviewer 未完成/未执行。当前预设关闭独立 reviewer，未将其记为通过。
