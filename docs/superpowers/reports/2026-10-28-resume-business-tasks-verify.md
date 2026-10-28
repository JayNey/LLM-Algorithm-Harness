# resume-business-tasks 验证报告

## 当前结论

待最终完整测试与集成审查确认。实现和文档已提交；不以中间测试结果代替最终结论。

## 范围与设计

- 对应 issue #306，用户明确选择继续 tweak 并使用独立分支 `tweak/20261028/resume-business-tasks`，涵盖四类 Worker 的跨模块协调与相应文件范围。
- 实验、基准、导入、A/B 在保存当前单元并退出后确认停止；确认前不恢复。原任务及业务关联保留，已持久化单元跳过。
- 实验检查点以位置区分同名模型/策略配置，基准以完整策略配置区分单元；A/B 保存确定性分组的单题结果；导入保存校验检查点并原子合并最终数据集。
- 数据库锁保护恢复与取消；新 Celery 标识隔离执行代际；重复投递只能认领一次；发布失败仅条件更新同代 pending。
- 导入认证库与业务库之间采用条件状态同步及提交失败补偿，不承诺跨数据库进程崩溃原子性。失联 Worker 的 paused 状态不自动视为停止确认。
- evaluation 保留原检查点、容量、归属和首次发布失败后重试原评估的契约；补充旧消息、旧终态与异常回调保护。

## 已有验证证据

- 失败域回归：1020 passed，覆盖异步提交、evaluation 启动重试、公开任务提交授权、五类型恢复、HTTP 端点和 UTF-8 契约。
- 相关集成与运行器回归：539 passed、2 skipped；随后另有 2 项旧 evaluation 终态/异常回调测试通过。
- 四类检查点测试：8 passed，覆盖跳过已持久化单元、费用和 token 不重复、同名参数组合隔离、并行队列暂停、小样本 A/B JSON 统计。
- `python3 -m ruff check src api tests` 通过；所有修改 Python 文件 Black 检查通过；`python3 -m compileall -q src api` 通过；`git diff --check` 通过。
- `comet classic openspec -- validate resume-business-tasks --strict --type change` 通过。delta 保留原场景标识并扩展非评估类型恢复语义。
- 首轮完整测试：3485 passed、25 failed、11 skipped，覆盖率 92.25%。失败已按独立问题域调查修复，包含首次发布失败重试、路由依赖及完整测试替身/编码契约；最终完整重跑进行中。
- `mypy src/ --ignore-missing-imports` 剩余 5 条错误；以 `git archive` 提取原始基线独立重跑，复现完全相同的 5 条错误，位于未修改的 `api/files/parsing.py`、`api/progress.py`、`api/services/cost_service.py`、`api/services/cost_alert_service.py`。本次修改未新增类型错误。

## 场景映射

- 五类型恢复和发布顺序、结果/进度保留：`test_resume_commits_pair_before_publish_and_preserves_progress`。
- 停止确认与 Worker 循环：`test_pause_requires_worker_stop_confirmation`、`test_worker_stops_confirms_resumes_and_ignores_old_delivery`、A/B `test_pause_resume_keeps_generation_and_rejects_old_finish`。
- 并发恢复、取消竞争及旧回调：`test_concurrent_resume_only_publishes_one_message`、`test_cancel_racing_resume_always_leaves_cancelled_pair`、`test_claim_is_unique_and_old_callbacks_cannot_change_resumed_task`、`test_old_broker_result_cannot_fail_new_generation`。
- 归属、非 paused、业务终态：`test_nonpaused_and_other_owner_cannot_resume`、`test_import_already_merged_cannot_be_paused_or_cancelled`，以及既有 evaluation 未关联记录测试。
- 发布失败及竞争：`test_resume_publish_failure_updates_pair`、`test_publish_timeout_preserves_competing_state`、`test_import_business_commit_failure_compensates_job_status`。
- 检查点、不重复执行和费用：`tests/test_business_checkpoints.py`。
- evaluation 回归：`tests/test_celery_tasks.py`、`tests/test_evaluation_workflow_contract.py`、`tests/test_evaluation_async_flow.py`。

## 审查与限制

实施分段审查已确认并修复同名组合身份、导入提交失败补偿和 A/B 非有限统计值问题。最终集成审查待记录。

验证采用真实 SQLite 会话、真实文件检查点，隔离 broker 与收费模型调用；未执行真实 broker 故障注入、付费模型调用或 PostgreSQL 实例验证。后台 Worker 使用共享卷与一致配置是恢复的部署前提，已写入部署文档。
