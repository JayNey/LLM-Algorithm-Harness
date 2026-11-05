# builtin-pricing-longest-prefix 验证报告

结论：PASS。Issue #351 核心验收完成，环境失败经针对性复验全部通过。分支 codex/builtin-pricing-longest-prefix，实现提交 91d3fd4。

## 完整性与正确性

- tasks 1/1 完成；单一既有能力 delta，无新增 API、依赖或架构协调。
- 生产改动仅 src/utils/pricing.py：builtin exact 后按长度降序匹配，保持 override exact → custom exact/prefix → builtin exact/prefix → unknown。
- tests/test_pricing.py 新增 30 个参数化用例。修改前 5 failed / 36 passed，修改后定价测试全部通过。
- 覆盖两个日期快照、gpt-4o-mini、相邻 Claude 别名、原始/逆序/轮转插入顺序、精确匹配、原模型标识、自定义及 exact override 优先级；既有测试覆盖文件加载、非法 JSON、未知定价。
- 离线 SDK 返回真实协议结构，真实 LLMClient 生成响应元数据和费用，真实 RunCostMonitor 结算 trace 并判断预算。各 1000 输入/输出 token：gpt-4o 日期模型 $0.02、turbo 日期模型 $0.04；$0.05 预算首次未超、累计三次超限。旧实现首次即错误计费 $0.09。

## 执行证据

- `pytest tests/test_pricing.py tests/test_llm_client.py tests/test_llm_client_cache.py tests/test_benchmark_run_budget.py tests/test_cost_strategy.py -q --no-cov`：161 passed。
- `pytest`：3892 passed、18 skipped、1 failed、22 errors，覆盖率 93.02%（门槛 90%）。原始日志 /tmp/issue351-full.log。
- 原始失败均为环境：18 个本地 HTTP/nginx 测试 socket.bind 被沙箱拒绝；broker 失败恢复测试也受 socket 权限影响；4 个 Anthropic 参数测试因全局 anthropic==1.5.0 与 pyproject 要求 <1 不符，httpx/httpx2 类型不兼容。
- 授予本地端口权限后，`PYTHONPATH=. pytest tests/test_deployment_readiness.py tests/test_evaluation_artifacts.py::test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription -q --no-cov`：15 passed。日志 /tmp/issue351-env-recheck.log。
- 临时 Python 3.11 环境 /tmp/issue351-venv 使用系统依赖，并安装 anthropic==0.125.0（符合项目约束，未改全局环境）。有本地端口权限执行 `PYTHONPATH=. /tmp/issue351-venv/bin/python -m pytest tests/test_strategy_provider_params.py tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http tests/test_api_cost.py::TestPricing::test_full_model_id_auth_and_validation_over_http tests/test_api_cost.py::test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery -q --no-cov`：16 passed（含原剩余 8 项错误及额外 8 项参数测试）。日志 /tmp/issue351-env-final.log。
- 完整测试原始失败项及错误项名称：
FAILED tests/test_evaluation_artifacts.py::test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription
ERROR tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http
ERROR tests/test_api_cost.py::TestPricing::test_full_model_id_auth_and_validation_over_http
ERROR tests/test_api_cost.py::test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]
ERROR tests/test_api_cost.py::test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[ab]
ERROR tests/test_deployment_readiness.py::test_nginx_runtime_pid_is_isolated
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/evaluations]
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/auth/login]
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/ws/progress]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[401]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[403]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[500]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[timeout]
ERROR tests/test_deployment_readiness.py::test_probe_is_get_without_client_credentials_body_or_query
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[401]
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[403]
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[500]
ERROR tests/test_deployment_readiness.py::test_probe_requests_do_not_hit_business_rate_limit
ERROR tests/test_deployment_readiness.py::test_websocket_upgrade_headers_survive_admission
ERROR tests/test_strategy_provider_params.py::test_self_consistency_controls_candidate_count_at_sdk_boundary[anthropic]
ERROR tests/test_strategy_provider_params.py::test_few_shot_controls_retrieval_without_leaking[anthropic]
ERROR tests/test_strategy_provider_params.py::test_reflexion_controls_context_on_generation_and_reflection[anthropic]
ERROR tests/test_strategy_provider_params.py::test_cache_uses_provider_params_but_not_strategy_controls[anthropic]
= 1 failed, 3892 passed, 18 skipped, 128 warnings, 22 errors in 577.40s (0:09:37) =

- `python3 -m build` 不可用（缺少 build.__main__）；采用同一 setuptools 后端的 `python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/issue351-dist .` 成功构建 wheel。
- black --check、ruff check（两个变更 Python 文件）、git diff --check、OpenSpec validate --strict 均通过。

## 一致性与审查

- 完整 delta 的 7 个场景均有对应回归覆盖；design.md 与实现一致，无漂移。Tweak 不要求独立 Superpowers Design Doc/plan。
- 独立 reviewer 审查最终实现、测试及所有 change 产物：无 actionable findings；无 CRITICAL/IMPORTANT 问题，无需接受偏差。
- 初次完整测试未整体全绿；所有 23 个失败/错误逐项在适当环境复验通过。未在临时环境重新运行整个 3932 项套件。
- 未更新外部单价，未使用真实模型服务或付费调用。Comet task 上下文插件因全局状态锁 EPERM 不可用，依技能约定不阻断。
- 未提交改动均为本次 Comet 状态与本验证报告。测试生成的空任务目录及零字节执行锁已清理。

## 归档交付选择

用户于 2026-11-05 明确选择 C：确认归档、立即推送当前绑定分支并创建关联 #351 的 PR。
