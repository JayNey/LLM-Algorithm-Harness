# LLM 调用采集验证报告

日期：2026-10-23。Change：`llm-call-collection`。分支：`codex/tweak/20261023/llm-call-collection`。基线：`63d7142d9e34d196dca0879da0d0b17b1cd66c71`。

## 结论

PASS。本次三项任务全部完成，三个新增要求、七个规格场景均有实现及测试覆盖，proposal 与 design 的目标一致，没有本次引入的 CRITICAL/IMPORTANT 或需接受的规格偏差。按用户明确选择继续 tweak；新增 capability 和超过六个文件的范围已经说明并获确认。使用完整验证；tweak 不需要独立 Superpowers Design Doc 或完整 plan，设计依据为 change 的 design.md。

## 实现核对

- `src/llm_client.py`：共用重试入口的每次 SDK operation 均通过 `_observe_operation`，OpenAI（含 local/SiliconFlow）和 Anthropic 均覆盖；perf_counter 仅测量该次 operation，finally 中隔离导入、计时、配置与写入异常。SDK 正常返回计成功，本地响应解析失败不会重新定义 SDK 请求结果。缓存和模型列表分支未进入采集。
- `api/monitoring/llm_metrics.py`：按部署 AuthSettings 选定共享数据库；缓存按 PID、绝对路径和保留配置区分，不缓存连接或凭证。初始化连接及写入 busy_timeout 为 100ms；缺少服务端配置的 CLI 仍能执行模型请求。
- `api/monitoring/store.py`：五个固定数值键保存起点、调用数、成功数、失败数、累计毫秒。单事务更新、单 SELECT 一致性读取，跨连接/进程共享并保留到重启后；不新增表或迁移。计数不按日志保留期裁剪，数据规模固定。
- `api/monitoring/service.py`：现有管理员 llm-stats/performance 查询读取持久化统计，保留用量登记和验证计数。接口明确 recorded_completed_attempts_shared_auth_database、best_effort、起点和遗漏范围；无样本成功率及平均耗时为 null。
- `tests/conftest.py`：将默认认证数据库路径隔离到每个测试的临时目录，防止测试中的模拟模型请求污染开发数据库。
- `api/documentation.py`、`docs/api-monitoring.md`：同步统计、重试与耗时定义、权限、部署共享路径要求、缺样本和采集故障口径。

## 场景与证据

1. 请求成功或失败：`test_generation_outcomes_at_provider_boundary` 对四个 provider × 成败组合断言调用数、结果、250ms 耗时、响应与异常脱敏。
2. 重试与退避：`test_retries_count_attempts_and_exclude_backoff` 明确两次尝试和一次成功/失败，平均 200ms；`test_real_openai_sdk_transport_retry_is_observed` 用真实 OpenAI SDK 与本地 MockTransport 验证 429 → 200，SDK 内建重试关闭。未发起收费的在线请求。
3. 非生成路径：`test_cache_and_model_list_do_not_count` 验证两次 generate 缓存复用及 list_models/check_connection 仅计一次生成请求。
4. worker 写入与 API 读取：`test_worker_process_writes_visible_to_api_store` 使用独立 Python 进程走客户端重试路径及默认配置写入；`test_llm_calls_persist_across_connections_without_request_payloads` 验证重新构造存储后计数/耗时保留；`test_llm_concurrent_writers_do_not_lose_updates` 验证多线程独立连接 40 次更新无丢失。
5. 无样本与权限：存储和 service 测试断言零计数、null 比率/延迟；`test_llm_statistics_are_real_and_admin_only` 从真实 HTTP 接口验证匿名 401、普通用户 403、管理员数值与 no-store。原验证/登记计数不增加生成计数。
6. 写入或计时失败：`test_collection_failures_preserve_result` 对写入、开始/结束计时、配置故障 × 原请求成败组合验证原结果及单次 SDK 调用；真实 SQLite 锁测试覆盖首次初始化和已初始化写入，恢复后继续计数；`test_unconfigured_cli_still_generates` 验证无服务端密钥仍可生成。
7. 敏感内容：provider 参数化测试验证提示、响应、密钥和错误正文不进入元数据；存储测试断言仅五个数值键、不产生请求日志；无新增 HTTP 写入入口。

## 实际执行

- RED：存储/service 的八项测试先因缺少计数方法和原占位响应失败；补齐实现后八项通过。采集测试先因缺少采集模块失败，补齐真实路径后通过。
- `python3 -m pytest -q -o addopts='' tests/test_api_monitoring*.py tests/test_api_documentation.py tests/test_llm_call_metrics.py tests/test_llm_client.py tests/test_llm_client_cache.py`：392 passed。
- `python3 -m pytest -q -o addopts='' tests/test_harness.py tests/test_offline_e2e.py tests/test_ab_testing.py tests/test_execution_logs.py`：58 passed。合计 450 项不同测试通过；未声称全仓库测试或全仓库覆盖率达标。
- 进入 verify 后再次运行客户端/采集三个文件：83 passed；`python3 -m compileall -q src api` 成功。
- 对本次十个 Python 文件执行 `black --check` 与 `ruff check`：通过。使用项目 Black 格式；纠正了 Ruff formatter 对原嵌套条件表达式的格式差异，最终无该处无关格式变动。
- `mypy src/llm_client.py api/monitoring/llm_metrics.py api/monitoring/store.py --follow-imports=silent`：三文件通过。
- `python3 -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir /private/tmp/llm-call-collection-wheels .`：构建 wheel 成功；检查 wheel 中包含 `api/monitoring/llm_metrics.py`。
- `comet classic openspec -- validate llm-call-collection --strict`：通过；build guard 十三项通过；`git diff --check` 通过。

## 已核对的环境及基线事项

- 直接调用 `/opt/homebrew/bin/pytest` 时，已有两个测试文件不能导入 `tests.test_api_monitoring`。改用 `python3 -m pytest` 后完成上述 392 项回归；无需源码修复。
- 扩展 mypy 到 service.py 会在原有任务耗时聚合 `aggregate(rows)` 处报 Sequence[RowMapping] 与 list[Any] 不匹配。将基线 service.py 单独导出再运行相同 mypy，复现同一错误；本次对应代码未改动。这是已有类型基线，不是新代码问题，也没有为此豁免本次验收要求。
- 测试输出包含既有 Pydantic/SQLAlchemy 弃用提示、测试模型类收集提示和相同数据的 SciPy 精度提示，不影响通过结果。
- 按 tweak 的持久化预设 `review_mode: off`，未派发自动独立代码审查。主会话已核对最终 diff 的正确性、隐私、事务原子性及故障边界；完整规格验证和测试照常执行。

## 工作区与交付

实现、测试和说明已提交三次：`fbd7e7a`、`0b4c138`、`6860f56`。verify 阶段的未提交文件仅为本报告及 Comet 自动状态/轨迹，均属于本 change。

用户随后明确选择 C：确认归档、推送当前绑定分支并创建 PR。`comet archive llm-call-collection` 已成功完成 6/6 步，主规格 `openspec/specs/api/llm-call-metrics/spec.md` 已同步，change 已移动到 `openspec/changes/archive/2026-10-23-llm-call-collection`。最终 archive guard 六项通过，`archived: true`、`verify_result: pass`、`branch_status: handled`。handled 表示交付方式已经确认；推送与 PR 创建在归档提交后执行。
