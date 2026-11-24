# 验证报告：bound-job-list-pagination

日期：2026-11-24。关联 issue：#515。工作区：`/Users/verstappen/LLM-Algorithm-Harness`，分支 `main`，基线 `eb9676007d1c8910502e8e8756eaca15ab10d508`。

交付补记：用户选择独立分支 PR 交付后，同一工作区已换绑 `codex/bound-job-list-pagination`，PR base 为 `main`。源码及测试内容未变，沿用本报告的实际检查结果；重新登记 Verify 仅用于更新归档提案的分支绑定。

## 结论

实现满足已批准范围及全部 delta 验收场景。4/4 任务完成，3/3 需求、8/8 场景已核对，无 CRITICAL、IMPORTANT、WARNING 或 SUGGESTION 实现问题。相关 SQLite/API 回归及真实 PostgreSQL 验证通过。尚未归档或 Git 提交。

| 维度 | 结果 |
| --- | --- |
| 完整性 | proposal、design、两个 delta specs 和 tasks 完整，任务全部完成，五个交付文件符合预设范围 |
| 正确性 | 三处 COUNT 与页查询共享筛选；数据库分页、必要字段投影、快照裁剪与兼容场景通过 |
| 一致性 | 保留 created_at/id 升序排序、响应字段及实验任务关联，详情与执行配置路径未改动 |
| 审查 | 主会话核对最终 diff；独立 reviewer 按已选 tweak 配置 `review_mode=off` 不适用，未声称独立审查通过 |

## 需求与场景映射

| 需求 / 场景 | 实现与证据 |
| --- | --- |
| 评估：历史增长不扩大单页实体加载 | `api/services/evaluation_service.py:list_evaluations` 使用 COUNT 与 LIMIT/OFFSET，load_only 排除 problem_ids。`test_page_entity_loads_stay_bounded_as_history_grows` 在 200/400 条历史中均只加载 20 个实体；`test_evaluation_page_omits_execution_only_problem_ids` 检查 SQL 与加载对象 |
| 评估：状态归属及同时间排序 | 页查询与 COUNT 共享 filters；`test_count_and_pages_share_owner_and_status_filters` 覆盖归属、状态与 offset；相同时间的 id 升序断言覆盖稳定排序 |
| 评估：空结果与越界页 | 相同测试覆盖未知用户、无匹配状态和 offset=999，空页只执行 COUNT 和页查询，无关联资源读取 |
| 实验与 A/B：大历史中的固定页大小 | `experiment_service.py:list_experiments`、`ab_test_service.py:list_tests` 使用数据库分页与 COUNT；参数化测试覆盖两种服务、200/400 条历史及实体上界 |
| 实验与 A/B：过滤与稳定排序 | 相同筛选与排序测试通过；`test_experiment_page_keeps_latest_owned_task_association` 验证当前页最新任务关联，排除他人、其他类型及页外任务 |
| 实验与 A/B：空页 | 参数化空页测试验证真实 total、零业务实体加载与无关联查询 |
| 配置：大快照仅返回摘要 | `api/datasets.py:public_dataset_config_sql` 在 SQLite 用 json_remove、PostgreSQL 用 JSONB #- 路径删除。`with_expression` 让 ORM 在加载时即只持有公开配置；快照测试验证裁剪、额外公开字段和原始持久化快照不变 |
| 配置：旧配置与空快照 | `test_job_page_preserves_legacy_and_null_snapshot_config` 验证缺失键及 null 语义，无额外逐行查询；两种数据库均真实执行通过 |

既有回归同时覆盖评估成本、操作能力、进度、任务启动/恢复、实验排队、A/B 执行及个人数据集快照，未发现因必要字段投影引入的惰性读取或响应回归。

## 实际检查

所有仓库内命令的 cwd 均为本报告所列工作区。

1. **缺陷复现**：先在修复前运行新增边界测试，真实观察到返回 20 条却加载 200/400 个业务实体，以及 ORM config 包含完整私有题目。日志：`/tmp/issue-515-red.log`、`/tmp/issue-515-evaluation-red.log`。初次测试夹具的 Evaluation 构造参数及 AsyncTask 必填字段错误已修正，后续复现结果为目标断言失败，未把夹具错误当作缺陷证据。
2. **查询边界回归**：`.venv/bin/python -m pytest tests/test_job_list_pagination.py -q --no-cov`：30 passed、7 skipped。跳过项为参数化时不适用的业务类型。日志：`/tmp/issue-515-pagination.log`。
3. **相关集成回归**：

   ```text
   .venv/bin/python -m pytest tests/test_job_list_pagination.py tests/test_evaluation_workflow_contract.py tests/test_api_evaluations.py tests/test_evaluation_service_async.py tests/test_evaluation_async_flow.py tests/test_generic_evaluation_submission.py tests/test_experiment_queue_safety.py tests/test_api_experiment_benchmark.py tests/test_dataset_references.py tests/test_experiment_task.py tests/test_ab_test_task.py tests/test_experiment_cancellation.py tests/test_business_task_resume.py -q --no-cov
   ```

   结果：486 passed、7 skipped、195 条弃用提示，70.16 秒，退出码 0。日志：`/tmp/issue-515-regression.log`。随后 Black 仅调整空白格式，无行为变化。
4. **PostgreSQL 真实执行**：`.venv/bin/python /tmp/issue_515_postgres_check.py`：26 个隔离数据库用例通过，复用同一测试文件的真实服务断言，覆盖三种列表、200/400 条历史、过滤、空页、快照裁剪/保留及实验任务关联。临时实例仅监听独立 Unix socket，结束后已停止并移除临时集群。日志：`/tmp/issue-515-postgresql-results.log`、`/tmp/issue-515-postgresql.log`。第一次启动被沙箱共享内存限制阻止，在取得工具执行授权后成功验证。
5. **静态检查**：ruff 检查五个变更 Python 文件通过；Black 逐文件 `--check` 全部通过；`git diff --check` 通过。
6. **类型检查**：`.venv/bin/mypy api/datasets.py api/services/evaluation_service.py api/services/experiment_service.py api/services/ab_test_service.py --ignore-missing-imports`：Success，4 个源文件无问题。初次未带 CI 使用的 `--ignore-missing-imports` 时，仅因 celery/scipy 缺少类型元数据失败；按 CI 策略重新运行通过，未修改依赖或忽略实现错误。日志：`/tmp/issue-515-mypy.log`、`/tmp/issue-515-mypy-ci.log`。
7. **OpenSpec**：`comet classic openspec -- validate bound-job-list-pagination --strict` 通过；apply 返回 all_done、4/4 完成。
8. **Build Runtime**：`complete-build` 已接受真实检查报告，并进入当前 `tweak.verify.run`，revision 6。验收复用上述有效证据，未为提交报告重复运行测试。

## 风险与验证边界

- COUNT 与深 offset 的数据库扫描开销仍随数据规模变化；本次保证应用接收的业务实体受页大小约束，且列表不接收完整冻结题库。
- COUNT 与页查询是两条语句，并发写入下沿用现有隔离级别，不保证新增的跨查询快照一致性。
- 未执行仓库全量测试、生产规模压力测试或真实付费模型调用；这些不是本次已批准验收要求。未将其记录为通过。
- 运行检查中产生的空执行锁文件已清理；未改动持久化业务数据、schema 或前端。

## 交付范围

实现：`api/datasets.py` 与三个 service；测试：`tests/test_job_list_pagination.py`。主规格将在用户确认归档后由 Comet 同步。变更说明位于 `openspec/changes/bound-job-list-pagination/walkthrough.html`。
