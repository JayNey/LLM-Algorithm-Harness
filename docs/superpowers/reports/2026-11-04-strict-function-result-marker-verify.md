# Issue #336：严格函数结果通道验证

Change：strict-function-result-marker。分支：comet/strict-function-result-marker。

## 改动与根因

Host 与 Docker function wrapper 都生成并传入本次随机 marker，旧解析器未找到 marker 时却接受 stdout JSON。现仅 result_marker is None 的明确 legacy 调用允许此回退。非法 payload 继续抛 SandboxExecutionError(runtime_error)，缺少 marker 同样为用例级 runtime_error；按既有聚合契约 SandboxResult.status 为 failed，all_passed 为 false。

## 回归证据

- RED：新增用例运行得到 4 failed、8 passed。Host 打印答案后 SystemExit(0) 原先 all_passed=True；显式 marker 缺失/错配未抛异常。
- GREEN：pytest tests/test_sandbox_executor.py tests/test_sandbox_docker.py --no-cov -q：63 passed、6 skipped。
- 真实容器：RUN_DOCKER_TESTS=1 pytest tests/test_sandbox_docker.py --no-cov -q：20 passed。Docker 29.7.2，python:3.11-slim 镜像 ae952e0a57138a4317b9b61caaa19a8217c2f356803f8d7e63aad08769950937。覆盖提前退出拒绝、合法返回、调试 stdout、stdin/stdout 及既有隔离/资源上限测试。
- ruff check 与 black --check：三个修改的 Python 文件通过。
- mypy src/sandbox_executor.py --ignore-missing-imports：成功，无类型问题。
- git diff --check：通过。
- 构建：python3.11 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/issue-336-dist：成功生成 llm_algorithm_harness-0.1.0-py3-none-any.whl。环境无可用 build.__main__，使用现有 pip/setuptools 构建。
- comet classic openspec -- validate strict-function-result-marker --strict：通过。

## 场景映射

- 函数打印调试信息：Host 原有 test_function_mode_keeps_debug_stdout_separate、真实 Docker test_real_docker_function_result_channel。
- 打印期望值后提前退出：Host test_function_print_and_clean_exit_is_not_a_return、Docker mock 与真实容器通道测试。
- 非法 payload：test_invalid_function_payload_never_falls_back_to_stdout（空、非 JSON、不完整 JSON、额外尾随文本）。
- 错误 marker：test_explicit_function_marker_never_falls_back_to_stdout（缺失、旧默认 marker、其他执行 marker）。
- 合法 JSON：test_valid_function_marker_takes_precedence_over_stdout，含 null、0、嵌套对象。
- legacy：test_legacy_function_result_without_explicit_marker。
- stdin/stdout：既有 Host stdin/stdout 测试与真实 Docker test_real_docker_stdin_stdout_does_not_require_function_marker。

## 一致性

实现与 proposal/design/spec 相符。使用 tweak 精简设计，不需要 full 工作流的 Design Doc/plan。本次触及三个实现/测试文件，无 public API、数据库 schema、依赖或跨模块架构变更。主规范尚无 execution-protocol；delta 使用 ADDED 的独立要求名，避免修改不存在的主规范或覆盖另一未归档 change。

## 全套测试与审查

独立只读审查覆盖基线 3dcaa58..df5e7f0，Critical/Important/Minor 均无，实现可合入；完整 pytest 成功退出（exit 0）：3762 passed、15 skipped、128 warnings，耗时 564.42s；覆盖率 92.92%，达到项目要求 90%。警告来自既有 Pydantic 弃用、TestCase 类收集等，未出现测试失败。审查明确保留既有 JSON NaN/Infinity 行为及同进程信任边界，不扩展为 marker 全面防伪改造；生产调用不会传空字符串 marker。

首次全套测试因沙箱禁止绑定本地端口出现 PermissionError；单独执行 tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http 已确认错误来自 listener.bind。中止该环境运行后，使用允许本地端口的环境重跑完整 pytest。中断运行还触发 pytest 临时目录 teardown KeyError，不属于产品源码失败。

## 最终结论

PASS。三个任务全部完成；能力要求及六项场景均有覆盖；实现遵循精简设计，无 spec 漂移。独立审查无待修问题。真实 Docker 验证完成，无环境豁免。用户已选择 C：归档、推送当前分支并创建 PR。Comet 归档 6/6 步完成，主 spec 已同步；完整归档提交的交付方式已确认为推送并创建 PR。
