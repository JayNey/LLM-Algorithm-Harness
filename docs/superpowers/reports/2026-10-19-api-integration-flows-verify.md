# API 集成流程验证报告

日期：2026-10-19（Asia/Shanghai）。Change：api-integration-flows。分支：comet/api-integration-flows。

## 完整性与验收映射
两个任务均已勾选。新增 tests/integration/test_api_workflows.py 包含 8 项离线集成测试：
- 注册 → 登录 → 存储密钥 → 创建并启动评估 → 查询持久化结果及异步任务进度。
- 上传题目 → 创建评估 → 执行至终态 → 下载 Markdown、HTML、CSV 报告。
- 创建实验 → 实际运行两个模型组合 → 查询对比结果，断言两组均解决测试题目。
- 并发创建和启动两个评估，再以两个线程运行真实任务体；沙箱入口 barrier 确认执行重叠，结果保持独立。
- 用户经 HTTP 暂停首单元 → 关闭应用 → 同库重建应用 → 恢复真实检查点；仅执行剩余单元，结果和费用不重复。
- 零预算不执行模型；首单元费用触达预算后暂停；恢复不得绕过原预算（参数化 2 项）。
- 同 ID 私有上传优先于公共题目；另一用户仍读取公共版本，无法执行他人的私有题目。

## 正确性与修复证据
首轮 7 项测试中 5 项通过，2 项稳定失败，均在修复前记录：
- 上传仅写认证库的私有 dataset，评估只读业务公共题库，导致上传题目无法执行。现在按 evaluation.user_id 读取私有 dataset 并验证完整 DomainProblem，再回退公共题库，未把私有数据复制到全局表。
- 实验 worker 构造 ExperimentService 时未注入认证服务，报 authentication service is not configured。现在初始化服务器配置的 AuthService，并在执行后释放服务 engine。
新增用户隔离回归后共 8 项集成测试全部通过。旧单元测试仅调整新增外部存储/认证依赖的 mock 边界。

## 验证命令与结果
- `python3 -m pytest tests/integration/test_api_workflows.py tests/test_celery_tasks.py tests/test_experiment_task.py tests/test_api_evaluations.py tests/test_api_files.py tests/test_api_experiment_benchmark.py tests/test_api_evaluation_results.py tests/test_task_manager.py tests/test_tasks_api.py tests/test_api_auth.py tests/unit/test_api_endpoints.py -o addopts= -q --tb=short`：1068 passed，5 项已有 Pydantic 弃用警告，耗时 89.73 秒。
- `ruff check src/tasks/evaluation.py src/tasks/experiment.py tests/integration/test_api_workflows.py tests/test_celery_tasks.py tests/test_experiment_task.py`：通过。
- `black --check src/tasks/evaluation.py src/tasks/experiment.py tests/integration/test_api_workflows.py tests/test_celery_tasks.py tests/test_experiment_task.py`：通过。
- `python3 -m compileall -q api src tests/integration`：通过。
- `python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/issue158-wheels .`：成功构建 llm_algorithm_harness-0.1.0-py3-none-any.whl。
- `comet classic openspec -- validate api-integration-flows --strict`：通过。
- `git diff --check`：通过。

## 一致性与范围
按 tweak 产物 design.md 核对：真实 HTTP、中间件、认证、SQLite、任务编排、策略执行、检查点、统计与报告均保留；所有测试数据和输出位于 pytest 临时目录。没有新增 API、schema 或依赖；修复服务于既有流程，skip_specs=true，无 delta spec，无需同步 main spec。Tweak 不生成独立 Superpowers Design Doc/plan，因此完整验证中相关检查不适用。

本套件替换 LLM、沙箱及消息/Redis 传输。模型替身提供固定用量与每次 USD 0.01 的费用，真实费用聚合和预算闸门仍执行；预算在单元边界检查，允许已执行单元费用超出极小预算后暂停。任务体在线程中实际运行，测试等待其结束再查询 HTTP 终态；本次不宣称验证真实 Redis、Celery 进程或 Docker，原 tests/test_async_task_integration.py 保持原有覆盖。定向回归显式关闭全仓覆盖率门槛，本次未宣称执行全仓测试或覆盖率检查。

## 最终集成审查
按 requesting-code-review 技能派发独立只读 reviewer，审查最终生产代码、8 项集成测试及 proposal/design/tasks。结论：未发现 CRITICAL 或 IMPORTANT 问题。已核对私有题目隔离与碰撞优先、实验认证及 engine 释放、并发执行重叠、恢复与费用幂等、预算恢复不绕过。reviewer 不重复运行全套测试，使用本报告的 1068 项实际回归证据。

## 结论
PASS：测试、构建、规格校验和最终集成审查均通过，无未解决问题。未提交内容均为本 change 的任务勾选、Comet 阶段状态和本报告，未混入用户改动。归档确认前 branch_status 保持 pending。

## PR #206 CI 修复补充
首轮远端 CI 在 UTF-8 前置检查停止：AST 编码扫描器把测试上下文入口 `environment.open()` 当成文件 IO，报告 8 处 missing encoding。后续覆盖率文件缺失来自前置测试停止，并非独立业务失败。
将辅助入口重命名为 `environment.session()`，保留真实文件 IO 的编码检查规则与门槛。修复前本地复现编码检查 8 处及 UTF-8 测试 1 failed / 17 passed；修复后 `python3 scripts/find_missing_encoding.py` 输出 0，`python3 -m pytest tests/test_utf8_io.py tests/integration/test_api_workflows.py -o addopts= --no-cov -q --tb=short` 26 passed。全仓 `ruff check .`、`black --check .`（309 个文件）与 `git diff --check` 通过。远端全矩阵结果以 PR 当前提交的 CI 为准。
