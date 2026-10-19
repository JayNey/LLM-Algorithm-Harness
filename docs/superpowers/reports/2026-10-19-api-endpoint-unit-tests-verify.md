# API 端点单元测试验证报告

日期：2026-10-19。Change：`api-endpoint-unit-tests`。分支：`comet/api-endpoint-unit-tests`。关联 issue：#158 第三节。

## 结论

PASS。3/3 任务完成，126/126 HTTP 方法/路径具有显式正常流程单元测试，另覆盖 1 个 WebSocket 端点。新增 803 个用例全部通过；新增测试与既有 API、任务管理、异步提交及评估回归共 1,285 个测试全部通过。API 行覆盖率 4,756/5,176 = 91.89%，高于 CI 的 81% 门槛；`api/routes` 行覆盖率 851/865 = 98.38%。生产代码未改变。

## 需求对照

- 每个 API 端点：`tests/unit/test_api_endpoints.py` 用显式方法/路径清单测试真实注册路由，清单守卫与应用路由逐项比对，包含别名以及 WebSocket。兼容 FastAPI 平铺和延迟包含路由。
- 正常流程：断言服务调用参数及 owner、嵌套请求模型字段、响应内容、状态码、204 空响应及下载内容/响应头；WebSocket 验证连接、快照、ping 和订阅释放。
- 错误处理：所有受保护 HTTP 端点覆盖未认证和无效 Token；所有管理员端点覆盖 403；有服务调用的端点验证 404 和内部异常脱敏；有 ValueError 映射的资源操作验证 400/404。
- 边界条件：空列表、重复 ID/策略、超长字段、0/负数、分页上下界、日志时间范围、缺少 run_id、非法 multipart/导入模式、导入进度分母为零、未知图表等。
- Mock 外部依赖：使用带 spec 的服务 Mock，替换数据库 session、任务管理器和异步进度流。TestClient 不进入 lifespan；额外阻断数据库引擎、LLMClient、SandboxExecutor 和 socket 连接，避免正常流程偷偷访问真实服务。
- 失败副作用：验证无效请求不调用业务操作；注册 run 失败撤销 evaluation；失败直接导入清理上传文件；外来 WebSocket task 以 4403 关闭并释放订阅。

## 验证证据

1. `MPLCONFIGDIR=/tmp/issue158-mpl pytest tests/unit/test_api_endpoints.py --no-cov -q`：803 passed（verify 阶段复跑同样通过）。
2. 回归命令：`MPLCONFIGDIR=/tmp/issue158-mpl pytest tests/unit tests/test_api*.py tests/test_tasks_api.py tests/test_runs_visibility.py tests/test_async_task_submission.py tests/test_evaluation_async_flow.py --cov=api --cov-report=term --cov-report=xml:/tmp/issue158-coverage.xml --cov-report=html:/tmp/issue158-html --cov-fail-under=81 -q`：1,285 passed，耗时 192.05 秒。
3. 上述回归命令受 pyproject 默认 `--cov` 累加影响，还统计了本轮未运行的 src 测试，因此汇总覆盖率门槛使进程返回非零；这是覆盖率范围问题，不是测试失败。随后按现有 CI 的相同口径运行 `python3 -m coverage report --include='api/*' --fail-under=81`，退出码 0，API 91.89%。未把失败的全仓覆盖率命令记录为成功。
4. `python3 -m coverage xml --include='api/*' -o /tmp/issue158-api-coverage.xml`：成功，API 数据同上。覆盖率文件属于本地临时输出，不提交生成报告目录。
5. `python3 -m compileall -q api tests/unit`：退出码 0。
6. `ruff check tests/unit/test_api_endpoints.py`、`black --check tests/unit/test_api_endpoints.py`、`git diff --check`：全部通过。
7. `comet classic openspec -- validate api-endpoint-unit-tests --strict`：通过。

## 完整性与一致性

proposal、design 和 3 项 tasks 均与最终实现一致。文件数超过阈值主要是 Comet 元数据；用户已明确选择继续 tweak。规模评估采用 full 验证，但此 change 没有生产行为改变，`.openspec.yaml` 声明 `skip_specs: true`，无需 delta spec 或 full 工作流的独立 Design Doc/plan。未发现规格漂移。

初始 tweak 状态 `review_mode: off`，因此按 comet-verify 跳过自动集成代码审查；未派发 reviewer。已检查最终 diff、需求映射、依赖隔离及错误/边界断言。无新增硬编码真实密钥、网络调用或不安全生产操作。CRITICAL、IMPORTANT、WARNING 均为 0。

验证结束时未提交项仅为本 change 的工作流状态和本验证报告。此报告不宣称全仓 src 覆盖率或 CI 远端执行结果。用户最终选择 C：归档并提交，推送当前绑定分支，创建 PR。
