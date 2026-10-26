# real-space-profiling 验证报告

日期：2026-10-26；结论：PASS。分支：comet/real-space-profiling。

## 完整性与一致性

- tasks.md 两项任务全部完成；实际业务变更为 3 个源码文件、2 个测试文件、1 个说明文档。其余文件为本 change 的 Comet/OpenSpec 产物及运行状态，无新增跨层架构协调。
- 修复既有空间评估占位实现，不新增能力或结果 schema；skip_specs=true，经 OpenSpec 严格校验通过，无 delta spec 需要同步。
- 完整验证依据本 change 的 design.md；tweak 不要求 Superpowers Design Doc 或完整 plan，对应检查不适用。实现遵循现有沙箱执行、超时、输出限制、隔离、清理链路。
- review_mode=off，为 tweak 默认值，跳过自动 reviewer；已核对最终 diff 的结果协议、采样校验、错误降级及隐藏测试隔离。

## 行为证据

真实 host 子进程测量：常量返回峰值 14,028 字节，256 MiB 预算评分 99.99；临时分配并释放 8 MiB 的实现峰值 8,391,054 字节（8.0023 MiB），评分 96.87。

24 项空间分析测试覆盖临时分配、编排传参、类方法、stdin/stdout、SystemExit(0)、脚本 __file__ 上下文、多公开用例峰值、隐藏用例隔离、宿主 tracemalloc 保持、缩放输入、评分公式、缺少样本、执行异常/错误答案/超时、关闭 tracing 及 Docker runner 两种协议和清理。

采样为 Python tracemalloc 分配峰值，包含代码加载和少量包装器开销，非 RSS，不覆盖未追踪的原生库内存；评分为配置预算余量，不代表理论最优比值或 Big-O。文档及结果 notes 明确这些范围。

## 命令及结果

- 最终相关回归：python3 -m pytest tests/test_code_quality tests/code_quality tests/test_sandbox_executor.py tests/test_sandbox_docker.py tests/reporting/test_quality_report.py --no-cov -q：129 passed，2 skipped，3 warnings，30.60s。
- 构建期间全量回归：python3 -m pytest --no-cov -q：3248 passed，11 skipped，14 个 setup errors，329.36s。错误均来自 tests/test_deployment_readiness.py 的 ThreadingHTTPServer 监听被沙箱拒绝（PermissionError: Operation not permitted）；该轮开始后增加的边界修复由上述最终相关回归覆盖。
- 对上述整个部署测试文件在允许本地监听环境重跑：python3 -m pytest tests/test_deployment_readiness.py --no-cov -q：14 passed，11.33s，无源码修改。
- python3 -m compileall -q src/code_quality src/sandbox_executor.py：通过。
- python3 -m mypy src/code_quality/space_analyzer.py src/code_quality/analyzer.py src/sandbox_executor.py --follow-imports=silent --ignore-missing-imports：3 files success。
- python3 -m ruff check src/code_quality src/sandbox_executor.py tests/test_code_quality/test_space_analyzer.py tests/code_quality/test_analyzers_coverage.py：通过。
- python3 -m black --check src/code_quality src/sandbox_executor.py tests/test_code_quality/test_space_analyzer.py tests/code_quality/test_analyzers_coverage.py：通过。
- git diff --check；comet classic openspec -- validate real-space-profiling --strict：通过。

## 环境限制

真实 Docker daemon 不可用（docker.sock 不存在），2 项现有真实 Docker 集成测试跳过。生成的 Docker runner 使用实际 Python 子进程执行，验证 function/stdin 两种协议和容器清理调用；不将此视为真实 Docker 资源限制验证。其余跳过来自现有依赖/在线测试门控，未修改其判断条件。

Comet task 上下文插件因 ~/.comet/plugins/state.json.lock 写入权限不可用，按技能的非阻断协议继续，无项目源码影响。

## 已重跑解决的全量错误明细

- tests/test_deployment_readiness.py::test_nginx_runtime_pid_is_isolated
- tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/evaluations]
- tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/auth/login]
- tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/ws/progress]
- tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[401]
- tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[403]
- tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[500]
- tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[timeout]
- tests/test_deployment_readiness.py::test_probe_is_get_without_client_credentials_body_or_query
- tests/test_deployment_readiness.py::test_business_errors_are_preserved[401]
- tests/test_deployment_readiness.py::test_business_errors_are_preserved[403]
- tests/test_deployment_readiness.py::test_business_errors_are_preserved[500]
- tests/test_deployment_readiness.py::test_probe_requests_do_not_hit_business_rate_limit
- tests/test_deployment_readiness.py::test_websocket_upgrade_headers_survive_admission
