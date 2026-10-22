# fix-api-restart-worker-recovery 验证报告

日期：2026-10-22。结论：PASS。

## 范围与工作区

- 分支：`hotfix/20261022/fix-api-restart-worker-recovery`。
- 修复提交：`89ac8da`。
- 修改三个服务的启动恢复条件和一个测试文件。其余文件为本 change 的 OpenSpec / Comet 工作流产物。
- `comet state scale` 按包含工作流产物的 17 个提交文件选择 full；实际实现/测试范围为 4 个文件，无接口、schema、依赖或架构变更。
- 进入 verify 时未提交改动仅为本 change 的 Comet 阶段状态，未发现无关改动。

## 完整性

- [x] tasks.md 的 3/3 任务完成，修复与测试已提交。
- [x] 1 个能力的 3 项 MODIFIED Requirements 均有实现及测试证据。
- [x] proposal 目标满足：API 重启不再把活跃 worker 所属的在途业务记录写成失败；实验正常收尾仍可关联结果。

## 正确性与规格映射

评估：`api/services/evaluation_service.py:187` 在处理 `pending/running` 候选时，直接以 `_is_enqueued` 判定是否有活跃任务，不再仅保护 `pending` 评估。

实验：`api/services/experiment_service.py:77` 保护有 `pending/running/paused` AsyncTask 的候选记录，不再只保护排队中的业务记录。`tests/test_api_restart_worker_recovery.py:127` 在 Celery 实验任务实际执行期间启动新 API lifespan，验证最终业务记录和任务均完成，且 `output_dir`、`completed_at` 已持久化，HTTP 结果查询返回 200。

基准：`api/services/benchmark_service.py:116` 使用同样的保护条件。恢复状态矩阵在 `tests/test_api_restart_worker_recovery.py:83` 覆盖三个服务，确保所有活跃任务状态下业务状态、任务进度、时间戳和关联保持不变。既有 `tests/test_benchmark_task.py` 的完成、结果指标、暂停和失败测试均通过。

原有场景由全套测试继续覆盖：

- 实验/基准提交与发布失败：`tests/test_async_task_submission.py`。
- 实验进度、暂停、执行失败与完成：`tests/test_experiment_task.py`。
- 基准进度、暂停、取消、指标与完成：`tests/test_benchmark_task.py`。
- 评估入队、进度、暂停、取消及完成：`tests/test_celery_tasks.py`、`tests/test_evaluation_workflow_contract.py`。
- 已入队 pending 记录跨重启：`tests/test_api_database.py`、`tests/test_api_experiment_benchmark.py`。
- 无活跃任务记录仍失败，暂停与终态记录不变：新增状态矩阵和 `tests/test_api_restart_worker_recovery.py:111`。

## 一致性

- [x] 实现符合 change 内 design.md：保护活跃关联，保持遗留失败恢复和 worker 收尾状态守卫。
- [x] delta spec 与实现及设计一致；主规格的“被中断的在途任务”仍适用于无活跃异步关联的遗留任务。
- [x] hotfix 使用精简设计，不适用单独的 Superpowers Design Doc / Plan 检查。
- [x] `review_mode: off`，依 hotfix 默认值跳过自动最终代码审查；完成变更范围、状态边界和安全检查，无新增密钥、权限绕过或危险操作。

## 验证命令与结果

1. RED：`python3 -m pytest tests/test_api_restart_worker_recovery.py --no-cov -q --tb=short`，修复前退出码 1：12 failed、43 passed。失败对应在途记录误判及实验完成关联丢失。
2. GREEN：相同命令修复后退出码 0：55 passed。
3. 全量离线：`python3 -m pytest -m 'not online'`，退出码 0：2933 passed、7 skipped、121 warnings，用时 330.49 秒；总覆盖率 91.78%，达到 90% 门槛。
4. 构建：`python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/api-restart-worker-wheel .`，退出码 0，生成 `llm_algorithm_harness-0.1.0-py3-none-any.whl`。
5. 编译：`python3 -m compileall -q api src`，退出码 0。
6. 修改文件的 Ruff、Black 检查和 `git diff --check`，均退出码 0。
7. `comet classic openspec -- validate fix-api-restart-worker-recovery --strict`，退出码 0。

RED/GREEN/全量测试完整日志分别保存在 `/tmp/api-restart-worker-red.log`、`/tmp/api-restart-worker-green.log`、`/tmp/api-restart-worker-suite.log`，为本机临时验证材料。

## 限制与结论

没有 CRITICAL、IMPORTANT 或需接受的偏差。重启时序回归使用真实数据库与 API lifespan，替换模型执行和配置解析边界，不连接真实 broker 或外部模型。本次不新增 worker 失联探测，API 重启本身不作为 worker 失败证据。

允许进入归档前最终确认；归档、主规格合并和远端交付尚未执行。
