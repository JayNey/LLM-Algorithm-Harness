# issue #352 验证报告

结论：PASS，实现与验收测试通过。分支 `comet/preserve-pending-drafts`，change `preserve-pending-drafts`。

## 完整性
2/2 tasks 完成；一个 delta requirement 的四个场景均已覆盖。业务改动为两个服务恢复查询，另更新四个测试文件；无 API、schema 或依赖声明变更，未触发架构升级信号。

## 正确性与场景映射
- 草稿跨服务重建和共享库第二实例：`test_unstarted_draft_survives_rebuild_and_starts_once` 验证真实创建、完整业务字段保留、重复恢复、实际 start 唯一任务及一次发布。
- 孤立执行：`test_pending_with_execution_evidence_is_not_a_draft` 覆盖 started_at、任务关联及无关联历史；原有恢复矩阵继续验证 running 无任务与历史终态任务的失败策略。
- 活跃及终态：原有恢复矩阵覆盖 pending/running/paused AsyncTask 和业务暂停/终态；新增无直接关联的活跃任务及 owner/type 隔离测试。
- 并发：`test_recovery_does_not_overwrite_concurrent_lifecycle_change` 在 UPDATE 执行前通过独立事务提交 start、completed 或新草稿，验证恢复不覆盖有效状态。现有跨进程入队及用户并发额度测试通过。
- HTTP 与监控：评估和实验 API 重启测试分别覆盖 pending 草稿与 running 孤立执行；草稿启动返回 202，重复返回 400；监控继续诚实统计 pending 草稿。

## 设计一致性
两个服务都以 owner/type/entity 相关 EXISTS 判断历史与活跃任务，单条条件 UPDATE 只将真正孤立的 pending/running 执行标为 failed。评估额外保留 async_task_id 作为提交证据。与 design.md 和 delta spec 一致。tweak 未创建独立 Superpowers Design Doc，按预设无需此产物。

## 实际验证
- RED：修复前重启回归 12 failed、59 passed，失败原因与 issue 和并发覆盖一致。
- 定向执行/并发：170 passed；扩展后的重启恢复：85 passed；数据库/HTTP：13 passed；实验和监控兼容回归：63 passed。
- 最终离线全量：`/tmp/issue352-py311/bin/python -m pytest -m 'not online'`，退出 0，3947 passed、18 skipped、128 warnings，527.42 秒，覆盖率 93.05%，满足 90% 门槛；src 覆盖率 91.84%（门槛 90%），API 覆盖率 94.83%（门槛 81%）。
- `python3 -m ruff check .`、`python3 -m black --check .`（382 文件）、`python3 scripts/find_missing_encoding.py`（0 隐式编码）、`git diff --check` 全部通过。
- 修改服务类型检查：`python3 -m mypy --follow-imports=silent --ignore-missing-imports api/services/evaluation_service.py api/services/experiment_service.py` 通过。
- `python3 -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/issue352-wheel .` 通过。
- `comet classic openspec -- validate preserve-pending-drafts --strict` 通过。

## 环境与验证边界
首次全量的本机 HTTP 端口绑定被沙箱拒绝，改在允许端口的环境运行；宿主 anthropic 1.5.0 不符合仓库 `<1` 要求，故在 Python 3.11 临时环境安装 anthropic 0.125.0 后完成最终全量，未修改宿主或项目依赖声明。全量期间发现并更新的旧草稿失败预期均已纳入最终通过的一轮。
附加深依赖 mypy 检查有 9 条基线错误（缺少 celery/kombu/scipy/yaml 类型信息、parsing.SafeLoader 和 cost_alert_service.metrics 类型问题），对主线原始服务文件同样复现；CI 范围 `mypy src/ --ignore-missing-imports` 有 4 条既有错误（api/progress.py:139、api/files/parsing.py:93、api/services/cost_alert_service.py:170-171）。这些额外检查未作为本次修改文件类型检查通过的依据。
未访问生产数据、真实模型或部署；实际数据库集成以 SQLite 为主，未运行真实 PostgreSQL 并发测试。

## 审查与流程
review_mode=off 为 tweak 默认配置，跳过自动 reviewer；已自行核对最终 diff 的状态谓词、owner/type 作用域、幂等性、终态保护与 SQL 方言无关表达式，未发现本次新增安全问题。
Comet 阶段推进与归档状态以 `.comet.yaml` 和公开 guard 实际输出为准。

验证阶段独立重跑重启恢复与数据库 HTTP 回归：98 passed、5 warnings，24.20 秒，退出 0。最终 diff 与所有四个 delta 场景一致，无未解决的 CRITICAL/IMPORTANT 问题。

## 归档交付
用户明确选择 B：归档后立即推送当前绑定分支 `comet/preserve-pending-drafts`，不创建 PR。主规格已同步，change 已归档到 `openspec/changes/archive/2026-11-05-preserve-pending-drafts`；archive guard 6/6 通过。
