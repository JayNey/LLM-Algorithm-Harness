# 用户评估并发准入验证

日期：2026-10-24。Change：`user-evaluation-concurrency`。分支：`tweak/20261024/user-evaluation-concurrency`。最终实现提交：`86c9ead`，基线：`e68f420`。

## 结论

PASS：完成 3/3 任务，覆盖 1 项新增要求和 4 个验收场景。最终只读集成审查无未解决的 Critical、Important 或 Minor 问题。采用 tweak 的简要 design.md，不要求完整工作流的独立 Superpowers Design Doc/plan。业务、测试及部署说明共 8 个文件，用户已明确选择继续 tweak。

## 行为与实现

- `api/config.py` 与 `.env.example`：每用户正整数限额 `MAX_CONCURRENT_EVALUATIONS_PER_USER`，默认 5。
- `src/task_manager.py`：create_task、enqueue_task、resume_task 在同一事务内获取共享数据库锁，再统计该用户 evaluation 类型 pending/running 任务并写入预留。SQLite 使用无匹配行 UPDATE 的写锁；PostgreSQL 使用稳定 signed bigint 参数的用户级事务 advisory lock。
- `api/services/evaluation_service.py`：恢复改用 enqueue_task，在消息发布前原子比较旧关联并提交新关联；防止立即消费消息时错误激活旧任务。
- `api/routes/evaluations.py`：超限启动返回 429，机器错误码 QUOTA_EXCEEDED。拒绝不发布消息，不留下新增活动任务，原草稿可重试。
- 草稿、暂停和终态不占用准入额度；恢复重新受限；状态转为暂停或终态后无需维护独立计数器。

## 规格场景与测试映射

1. 跨进程同时提交：test_independent_processes_share_one_remaining_slot，4 个独立 Python 进程、独立 engine、同一 SQLite 文件，在限额 1 下仅一个成功。初始 RED 显示 4 个全部成功；GREEN 验证限额生效。
2. 不同用户独立：test_users_and_other_task_types_have_independent_capacity，甲满额不阻止乙，非评估任务不计入额度。
3. 状态和恢复：test_status_controls_admission、test_service_start_async_create_and_resume_use_gate、test_same_task_resume_rechecks_capacity_and_keeps_pause_on_rejection；超限原地恢复保持 paused，额度释放后恢复成功。
4. 所有提交入口与失败回滚：test_full_user_rejected_without_candidate_or_publication、test_publish_failure_releases_capacity、test_link_failure_rolls_back_capacity。HTTP 覆盖 test_http_start_reports_quota_and_preserves_draft。竞争恢复覆盖 test_competing_resumes_do_not_republish_same_task；立即 worker 读取覆盖 test_resumed_evaluation_is_linked_before_worker_can_receive_message（先 RED，再修复为 GREEN）。

## 验证证据

- 最终增量回归：`python3 -m pytest tests/test_user_evaluation_concurrency.py tests/test_evaluation_service_async.py tests/test_task_manager.py tests/test_evaluation_workflow_contract.py tests/test_evaluation_async_flow.py tests/test_api_evaluations.py tests/test_tasks_api.py tests/test_deployment_config.py tests/test_utf8_io.py -q --no-cov`：239 passed，7 warnings，含 21 项新准入测试。日志 `/private/tmp/user-evaluation-concurrency-complete-targeted.log`。
- 全量离线复验：`python3 -m pytest -m 'not online'`：3115 passed，8 skipped，127 warnings；覆盖率 91.88%，通过 90% 门槛。日志 `/private/tmp/user-evaluation-concurrency-final-suite.log`。此轮在最终恢复关联修复前启动；该最终修复以随后 239 项增量回归及只读审查验证，不将该轮全量结果冒充最终提交的全量执行。
- 首轮全量：3111 passed、2 failed。失败为 TestEnvExample.test_covers_settings_fields（新配置遗漏）与 test_repository_has_no_implicit_text_file_or_subprocess_encodings（测试子进程未显式 UTF-8）；均已修复，随后全量通过。
- 最初直接调用 pytest 时监控测试因缺少仓库导入路径收集失败；改用 CI 的 python3 -m pytest 入口后正常收集执行。
- `ruff check .`：通过。`black --check .`：338 files unchanged。`python3 -m compileall -q api src`：通过。`comet classic openspec -- validate user-evaluation-concurrency --strict`：通过。`git diff --check`：通过。
- 剩余 warnings 为现有 Pydantic/pytest 等弃用与收集提示，不存在未解决的测试失败。

## 集成审查与边界

只读审查范围为 `e68f420..86c9ead`，已接受并修复普通评估恢复的发布前关联问题。下列范围逐项判定：

- 暂停/取消的物理停止时机：保持既有单元边界停止语义。本次约束是持久化 pending/running 准入预留，并非瞬时物理执行数量。
- worker 重复投递/重放：现有消息身份协议未修改；不将准入功能解释为执行去重协议。
- 通用 `/tasks` 的实体归属与参数身份校验：审查确认存在既有安全边界缺口（接口接受任意 evaluation 引用，worker 按 Evaluation.async_task_id 取任务）。应单独修复该权限/消息身份问题；本次未引入该缺口，也不声称完成这方面安全加固。
- 通用 `/tasks` 路由超限错误映射：仍使用原 ValueError→400 映射；本次 429 契约针对 evaluation 启动入口，通用任务准入检查同样执行。

本地没有 PostgreSQL 服务，Docker daemon 也未运行。PostgreSQL 分支通过真实 Session 拦截服务器专用语句的测试验证锁参数稳定性、参数绑定和锁先于计数；未执行真实 PostgreSQL 并发事务，不以此替代生产数据库集成验证。宕机遗留 pending/running 行保守占用额度，沿用既有恢复处理。

## 交付状态

代码与任务已提交，归档前仅有验证报告及工作流元数据改动。用户已明确选择 C：确认归档、创建唯一归档提交、推送当前绑定分支并创建 PR。由 comet-archive 依次完成主规格合并、change 目录移动及所选远端交付，不合并或删除分支。
