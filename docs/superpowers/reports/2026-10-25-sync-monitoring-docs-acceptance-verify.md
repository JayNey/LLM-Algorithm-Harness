# 监控文档与验收记录同步验证报告

- Change：sync-monitoring-docs-acceptance。
- 分支：comet/sync-monitoring-docs-acceptance；基线 e700646797712357fb215e2630f8c6e03710caec。
- 实现提交：fc5d325。
- 结论：文档同步检查 PASS；目标部署环境验收未执行。
- Issue 记录：https://github.com/JayNey/LLM-Algorithm-Harness/issues/157#issuecomment-6397989911

## PR #277 合并冲突复验

本节是合并 main `1624471a7cc74ef3cbf7654e1e39ca0c62f63612` 后的最新结果；下文初次验收记录仍对应 e700646 基线，不能用旧基线说明覆盖最新主线行为。

- 两处文本冲突为 docs/api-monitoring.md 与 docs/deployment/deploy.md；以主线的 pending_issues=[]、逐项验收清单、生产 nginx readiness 准入和可用性告警为准，补入本 PR 的接口差异、采集边界与验收报告链接。
- api/documentation.py 自动合并，保留主线 pending_issues=[] 示例及本 PR 指标说明。监控 service.py、nginx.conf、docker-compose.prod.yml 与本次合入的主线逐字节相同；无额外运行时行为修改。
- 运行 `python3 -m pytest tests/test_api_documentation.py tests/test_api_versioning.py tests/test_api_monitoring*.py tests/test_api_readiness.py tests/test_deployment_config.py tests/test_deployment_readiness.py tests/test_execution_logs.py tests/test_llm_call_metrics.py tests/test_user_call_limits.py tests/test_user_call_metering.py tests/test_monitoring_queue_integration.py tests/test_monitoring_container_integration.py --no-cov -q -rs`：515 passed、2 skipped、98 warnings、14 setup errors，119.36 秒。14 项错误均位于 nginx 测试 fixture 的本地 socket.bind，原因是沙箱拒绝监听临时端口（PermissionError: Operation not permitted），不是断言失败。
- 使用允许本地端口的环境运行 `python3 -m pytest tests/test_deployment_readiness.py --no-cov -q`：14 passed、1 warning，10.00 秒。相同代码上的上述 14 项环境错误已全部验证通过，无需产品修复；两次运行不重复合计，最终覆盖 529 项通过、2 项跳过。
- 两个跳过项仍为未显式启用的真实 Redis/worker 和 Docker 观测；未新增真实供应商、PostgreSQL 或生产部署验收。
- black --check、ruff check api/documentation.py、compileall api、git diff --check、文档本地链接及冲突标记检查通过。只读比较确认主线部署/监控运行时文件完整保留。

## 初次验收（合并前）

## 六项检查

1. 任务：1/1 完成；更新三个交付文件、当前报告及 issue 评论。
2. 范围：仅 OpenAPI 说明/示例、监控与部署指南及工作流产物；无路由/权限/行为变更，无 delta spec，skip_specs: true。冻结 OpenAPI 基线保持原样。
3. 构建/静态检查：python3 -m compileall -q api src；python3 -m black --check api/documentation.py；python3 -m ruff check api/documentation.py；git diff --check；comet classic openspec -- validate sync-monitoring-docs-acceptance --strict，全部通过。python3 -m pip wheel --no-build-isolation --no-deps --no-cache-dir --wheel-dir /tmp/sync-monitoring-docs-dist . 成功构建 llm_algorithm_harness-0.1.0-py3-none-any.whl。
4. 测试：相关回归 512 passed / 2 skipped，模型目录专项 19 passed / 40 deselected；具体命令及边界见下文，未执行全量测试。
5. 安全：仅文档更新，无新凭据、探针调用、授权路径或外部业务请求；issue 评论只含公开契约与验证结果。
6. 集成检查：按状态 review_mode=off 跳过自动独立 code reviewer；主会话逐项对照 routes/monitoring.py、monitoring/service.py、probes.py、store.py、execution_logs.py、src/task_manager.py 与 Compose 审阅最终 diff，未发现正确性、安全或边界问题。没有声称完成独立审查。

## Verify 阶段复核

规模评估统计 16 文件（含 12 个 Comet/OpenSpec 元数据），实际交付仅三处文档/说明及一份验收报告、1 个任务、0 delta spec，因此按 comet-verify 覆盖机制采用 light 六项检查。复核 proposal/design/tasks 及最终提交 diff；verify 阶段重跑 compileall、black --check、ruff check、git diff --check 和 OpenSpec strict validate 全部通过。相关测试已在最终 Python diff 上执行，无新增行为或测试改动，无需重复跑同一测试集。issue 评论通过 GitHub API 回读，确认保存内容与结果一致。

## 工作区与流程说明

入口工作区干净，用户选择新建分支。全部 diff 可归因于本 change，无用户既有改动。Tweak 无行为变更，使用精简 design.md，不需要 Superpowers Design Doc/plan。用户已确认选项 3：归档、创建本地归档提交、推送绑定分支并创建 PR。Comet 归档 6/6 步成功，归档目录为 openspec/changes/archive/2026-10-25-sync-monitoring-docs-acceptance；无 delta spec，主规格不变。branch_status=handled 记录该交付选择，远端执行结果以 GitHub PR 为准。

comet task 上下文插件因全局 state.json.lock 权限返回 EPERM，按 skill 的“插件失败不阻断变更”继续；未使用或反馈任何记忆条目。结束时 comet task --complete 重试成功，返回空 context。首次创建分支因 Git 元数据写权限失败，经沙箱升级重试成功。OpenAPI 手动断言时 Matplotlib 无可写全局字体缓存，自动使用临时缓存后通过，不属于产品行为失败。历史报告仍保留其当时结论，本报告是当前基线的补充记录。

## 接口、证据与部署限制

## 文档与验收记录同步（2026-10-25）

本次以本地代码基线 `e700646797712357fb215e2630f8c6e03710caec`（含 readiness 实现 #274）核对，在 `comet/sync-monitoring-docs-acceptance` 同步 OpenAPI 说明、`docs/api-monitoring.md`、`docs/deployment/deploy.md`。这是该基线的验证记录，不声明已覆盖之后的远端提交。2026-10-22 评论反映当时状态，其中的缺项已有后续实现；原文保留供追溯。

### 接口差异
- `/api/v1/health` 是公开 API 存活检查；综合诊断为管理员 `/api/v1/system/health`。公开 `/api/v1/health/ready` 已实现：数据库与迁移通过返回 200/`{"status":"ready"}`，未通过返回 503/`{"status":"not_ready"}`，1 秒响应预算及 1 秒进程缓存，响应 no-store。它仅证明基础数据库就绪，不包含队列、worker、沙箱或供应商。
- 除 readiness 的直接 status JSON 与日志下载外，监控成功 JSON 使用 `success/data/message` 包装；组件故障需读 `data.status`，不能仅凭 HTTP 200 判断。
- 日志是保留的安全事件，列表用 `items/total/limit/offset`；下载为 text/plain 的 JSONL 附件 `task-logs.jsonl`，不是完整 stdout 文件。
- broker waiting、数据库 pending、回复 worker reserved 分开展示，不相加；queued 列表仍为持久化 pending。

### 相对旧评论已实现的范围
- Redis 配置队列各优先级分桶 LLEN 等待数；带固定标签沙箱容器 CPU/内存观测（两类探测均需显式启用）。
- 异步任务生命周期与评估/导入进度事件采集；持久化 AsyncTask 的任务墙钟耗时和正常完成率，涵盖 evaluation/experiment/benchmark/import，不代表算法准确率。
- 真实生成 SDK 尝试次数、成功率、平均时延与可选窗口；worker/CLI 缓存快照及按汇总 hits/misses 计算的命中率。共享认证库采集均有覆盖与 best-effort 边界，不是全群集精确总账。
- SQL 统计扩展至当前 API 实例绑定的业务服务及 auth/file/monitoring 来源，不包含其他进程或数据库服务端全局流量。
- 用户评估并发查询，以及 UTC 日/月生成 SDK 尝试计量和可选强制限额。失败、重试各计一次；不等于所有 HTTP 请求日/月限流。
- 管理员 `/system/config` 显式白名单配置查询；`/config/providers` 默认静态目录，传入本人 api_key_id 才动态枚举，失败不回退；枚举成功不保证生成成功。

### 本次实际验证
1. `python3 -m pytest tests/test_api_documentation.py tests/test_api_versioning.py tests/test_api_monitoring*.py tests/test_api_readiness.py tests/test_deployment_config.py tests/test_execution_logs.py tests/test_llm_call_metrics.py tests/test_user_call_limits.py tests/test_user_call_metering.py tests/test_monitoring_queue_integration.py tests/test_monitoring_container_integration.py --no-cov -q -rs`：**512 passed、2 skipped、98 warnings**，122.97 秒。覆盖文档示例、冻结 v1 兼容、权限/脱敏、指标边界、真实本地 SQLite schema/迁移故障及部署配置。
2. `python3 -m pytest tests/test_api_evaluation_options.py -k monitor_models --no-cov -q`：**19 passed、40 deselected、5 warnings**，30.68 秒；供应商枚举使用测试替身。
3. OpenAPI 手动断言确认公开 health/readiness、HTTPBearer 管理员端点、readiness 503 示例及更新的指标说明；`black --check`、`ruff check`、`compileall`、wheel 构建、`git diff --check` 与 OpenSpec strict validate 通过。冻结契约文件未重写。警告为现有依赖弃用/fixture 提示。

### 尚未完成部署验收
- 本次未设置 `MONITOR_QUEUE_TEST_BROKER` 与 `MONITOR_CONTAINER_TESTS=1`，两项真实基础设施检查跳过。未执行真实 Redis/Celery、Docker、PostgreSQL、远程供应商或多主机端到端验收；上面的通过数不是这些环境的通过证据，也不是全量测试结果。
- 默认 Compose 的 API healthcheck 仍检查存活路径，未自动切换到 readiness。
- 默认 Compose 没有跨 API/worker 共享认证 SQLite 的专用命名卷；部署方需让各进程实际共享 AUTH_DATABASE_PATH 对应的存储、配置一致密钥和额度，并验证采集可见性。仅共享 DATABASE_URL 不足以共享日志/LLM/缓存/用户计量。
- worker 回复只覆盖收到回复的节点；API Docker context 不证明目标 worker 沙箱可用。日志与指标是有界保留/采集，null 和缺测不能补零。

本次只同步文档与验收证据，保留 issue 开放及原清单，待目标部署环境逐项验收后再判断是否关闭。完整报告路径：`docs/superpowers/reports/2026-10-25-sync-monitoring-docs-acceptance-verify.md`。
