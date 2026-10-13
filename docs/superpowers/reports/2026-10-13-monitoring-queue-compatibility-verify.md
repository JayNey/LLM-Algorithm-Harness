# PR #174 队列基础兼容验证报告

日期：2026-10-13（Asia/Shanghai）。主线基线：`016f130d1ee6cdd2b35bd7ca47bd308bc3c61b66`，包含 PR #179。分支：`tweak/20261011/system-monitoring-foundation`。使用用户指定的增量 Tweak；更新原 PR #174，关联 `Refs #157`。

## 实现与主线兼容

- 将本 PR 的三个功能提交重放到最新 main，保留新任务 router、启动时的会话工厂初始化和关闭时的 engine.dispose，以及 database_url、实验/基准/A/B runner factory 等已有接口。HTTP 任务依赖绑定各自 app 的实际工厂，防止多个应用并存时全局工厂切换导致串库；异步监控绑定同一个 task engine。
- 保留默认 legacy_evaluation 来源，新增 task_source=async_task。旧来源只读取 async_task_id IS NULL 的 Evaluation，异步来源直接读取 AsyncTask，关联任务不双计。system/status 保留旧字段，新增 async_task_* 字段；两源分别读取，不提供相加后的全局原子总数。
- 每源的聚合与分页使用同一只读快照。SQLite 显式 BEGIN，PostgreSQL REPEATABLE READ；故障为 unavailable/null，不冒充零任务。SQL 仅投影安全字段和有界数值进度，未知类型/状态归为 other；不读取完整 progress、错误、参数或 Celery ID，不轮询 TaskManager/Celery/Redis，不提交任务状态。
- PR #179 的队列基础已合并，Redis/worker 尚未联网探测，状态改为 not_checked，并明确 infrastructure_available 只表示代码存在。评估 worker 仍返回 mock；real_evaluation_available=false，不能将 completed 视为真实 LLM 评估成功。
- 同步 API、认证、文件、监控和 README 文档，说明任务/结果发布、日志与指标作用范围。SQL 指标仍只覆盖评估服务 engine 的游标执行，异步、实验、基准和 A/B 独立 engine 未全部纳入。

## 验证与审查

- 监控及队列相关回归：**252 passed**。
- 新增任务快照：**48 passed**；新增 HTTP 集成：**19 passed**。覆盖实际 POST /tasks（仅替身发送任务）、旧评估共存、两来源计数、权限与非法参数、安全进度、监控零轮询/业务库零写入、双应用隔离和关闭顺序。
- 最终全量离线：**1599 passed、4 skipped**，覆盖率 **93.96%**，原 **90%** 门禁不变，耗时 **144.55 秒**。执行 python -m pytest -m 'not online' --cov --cov-report=term --cov-report=xml -o faulthandler_timeout=60。保留本地原始日志 /private/tmp/llm-harness-174-queue-full.log；在线提供商验证未运行。
- Ruff、Black、显式编码扫描（0 处隐式编码）、OpenSpec strict 校验通过。mypy src：92 文件通过；监控/路由：9 文件通过；main 的应用工厂及依赖：1 文件通过。
- Bugbot 独立审查本 PR 对 main 的完整差异，**无新增发现**；审查者运行相关 **126 项测试通过**。GitHub 未解决行内审查线程为空。
- 当前 main 的 CI：run 38335757747，**10 项全通过**，包含 Ubuntu/macOS/Windows × Python 3.11/3.12 六组测试。本 PR 新提交 CI 在推送后另行核对，结果记录在 PR 描述。

## 调试与 Runtime 检查

旧健康测试仍期待 not_configured；在队列基础已存在后，应期待 not_checked 与明确的 mock 标记。新增 HTTP 只读断言精确允许 Alembic 对 alembic_version 的 PRAGMA schema 读取，不允许状态写入。补齐 main 原有返回类型注解后，局部严格类型检查通过。

上游 #179 提交的 .cursor/skills/comet 是指向另一台机器的失效符号链接。Runtime 默认仓库输入扫描因此拒绝运行；本轮保留上游文件，在本地忽略的 .comet/check-policy.json 为实际编译/67项定向测试命令声明项目文件输入。目录声明会将 __pycache__ 纳入指纹，全量测试并行时首次实际定向检查虽全部通过但输入不稳定；改为明确的普通项目文件清单、全环境指纹并在工作区稳定后执行。验证命令不依赖 HEAD/index；Git 元数据之外的源码、测试、配置、数据、规格和文档仍被绑定，不降低测试门禁。该本地策略不进入 commit 或 PR。

最终 Runtime 实际编译与 **67 项定向测试**分别在 build/verify 成功执行，输入前后指纹一致，未复用旧结果：build 日志 d6a72bec-5ae2-496b-8520-c7c65c924d15.log，verify 日志 d1aec547-4a8a-49da-8ee5-2fe8d235f241.log。build 守卫 **14/14**、verify 守卫 **5/5** 通过，由守卫推进到 phase=archive、verify_result=pass；保持 branch_status=pending、archive_confirmation=pending，没有手工伪记 pass 或自动归档。

## 规格与设计映射

- 管理员/所有者隔离：原身份伪造与私有日志回归，以及 test_async_source_requires_authentication_and_server_selected_admin。
- 队列基础存在但评估模拟：test_actual_task_and_legacy_routes_coexist_and_linked_tasks_are_not_double_counted、test_async_progress_is_safe_and_does_not_claim_real_worker_results。
- 只读数据库与失败空值：test_monitoring_does_not_poll_queue_or_modify_business_records、原业务健康探针回归，以及两源连接失败测试。
- 有界快照与一致性：test_counts_cover_matching_source_before_pagination、test_count_and_page_share_snapshot_during_concurrent_commit。
- 工厂/生命周期：test_simultaneous_apps_keep_http_tasks_and_monitoring_on_each_actual_engine、test_lifespan_closes_monitor_then_services_and_disposes_actual_task_engine。
- SQL 指标、日志脱敏与窗口完整性：沿用 database_metrics/store/service 回归并由本轮全量重新验证。
- Docker 预检成功、不可用、超时与答案失败：沿用 test_sandbox_executor 与监控探针回归；无宿主回退。

本次增量的 proposal、design、delta specs 与实现一致；Tweak 不要求另建完整技术设计或实施计划。未发现缺失验收场景或规格漂移。

## 限制与交付

- SQLite/HTTP 实际运行，PostgreSQL 仅离线 SQL 编译与边界检查，无实连接验证。
- 本机真实 Docker 最小预检返回不可用，没有回退 host；本机容器成功路径未实测。
- Redis/worker 无联网可用性验证，模拟 worker 不构成真实执行或 LLM 性能证据。#149 仍未完整完成，#157 的 worker/LLM/缓存/容器指标与新配额策略仍需后续接入。
- 自有提交和相对 main 的 PR 差异排除 .comet/.claude/.codex/.agents/skills-lock.json；上游已存在的流程文件不由本 PR 修改。保留推送前安全分支，使用显式 force-with-lease 防止覆盖他人远端更新。
- 更新同一个 PR #174，等待其当前头全部平台 CI；不自动合并或关闭整个 #157，change 保留待归档确认。
