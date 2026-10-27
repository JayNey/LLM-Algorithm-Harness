# 真实评估工程质量检查矩阵（#231 / T16）

## 本轮基线与验收口径

执行日期：2026-10-27（Asia/Shanghai）。基于 [PR #286](https://github.com/JayNey/LLM-Algorithm-Harness/pull/286) 的提交 `545d62d46ef5c237731d9e57c9fddb7159665a0d` 创建分支 `codex/tweak/20261027/evaluation-quality-gates-completion`，合入当时最新 main `b86d65eff2d2a76fdd39f54fe7b2794b9e3dc955`，验证代码提交为 `48ea717b5526cc8198f1b395e4285e58263f8564`。

本轮新增内容为检查记录、原始日志及工作流文档；`api/`、`src/`、`tests/`、`frontend/`、`pyproject.toml` 和 CI 配置相对上述 main 无差异。没有修改认证、资源隔离、评估行为、mypy 的 Python 3.10 目标或任何覆盖率门槛。源码树 ID、环境版本、命令起止时间、退出码及日志行号见 [commands.json](assets/issue231/commands.json)，完整输出（归档时仅去除 ANSI 色码、行尾空白及末尾空行）见 [execution.txt](assets/issue231/execution.txt)。记录的代码 SHA 是实际执行时 HEAD；后续仅文档或 Comet 提交不冒充重新运行。

## 环境与复现

- 宿主 Python 3.11.16、Node v26.8.1、npm 11.19.0；定向 Python 测试及前端四项检查使用宿主环境。
- 隔离后端环境：`uv venv /tmp/issue231-py311 --python /opt/homebrew/bin/python3.11`，再执行 `uv pip install --python /tmp/issue231-py311/bin/python -e '.[dev]'`。通过 `PATH=/tmp/issue231-py311/bin:$PATH` 选择此环境，再执行下列原始命令；不覆盖 mypy Python 目标。
- 隔离环境 mypy 2.4.0、SQLAlchemy 2.1.6、redis 8.1.0、Pydantic 2.14.1、pytest 9.1.1、coverage 7.17.0、ruff 0.17.3、Black 26.10.1；完整包版本见 JSON。
- 定向测试显式 `--no-cov`；全量 pytest 后顺序读取同一轮 coverage 文件。全库统计不使用定向测试的覆盖率。

## 已执行检查

| 检查                 | 实际命令（前端在 frontend/）                                                                                                                         | 结果                                             | 退出码 |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------ |
| 指定 API mypy        | 下方原始命令                                                                                                                                         | 3 个源文件通过                                   | 0      |
| CI mypy              | `python3 -m mypy src/ --ignore-missing-imports`                                                                                                      | 98 个源文件通过                                  | 0      |
| issue ruff           | `python3 -m ruff check api/ tests/test_api_evaluation_options.py tests/test_evaluation_workflow_contract.py tests/integration/test_api_workflows.py` | 通过                                             | 0      |
| CI ruff              | `python3 -m ruff check .`                                                                                                                            | 通过                                             | 0      |
| CI Black             | `python3 -m black --check .`                                                                                                                         | 351 文件无需修改                                 | 0      |
| 编码检查             | `python3 scripts/find_missing_encoding.py`                                                                                                           | 隐式文本编码 0                                   | 0      |
| 定向 Python          | `python3 -m pytest <16 个文件，见 JSON> --no-cov -q`                                                                                                 | 382 passed，5 warnings                           | 0      |
| 全量非 online Python | `python3 -m pytest -m "not online"`                                                                                                                  | 3366 passed / 11 skipped / 128 warnings，461.94s | 0      |
| src 覆盖率           | `python3 -m coverage report --include="src/*" --fail-under=90`                                                                                       | 91.38% ≥ 90                                      | 0      |
| api 覆盖率           | `python3 -m coverage report --include="api/*" --fail-under=81`                                                                                       | 94.86% ≥ 81                                      | 0      |
| 前端单测             | `npm test`                                                                                                                                           | 257 passed，0 failed                             | 0      |
| 前端 lint            | `npm run lint`                                                                                                                                       | 0 errors，2 条既有 warnings                      | 0      |
| 前端类型             | `npx tsc -b`                                                                                                                                         | 通过                                             | 0      |
| 前端构建             | `npm run build`                                                                                                                                      | 通过，893ms；既有大 chunk 提示                   | 0      |

指定 API mypy 的完整命令：

```sh
python3 -m mypy api/evaluation_options.py api/services/evaluation_options_service.py api/routes/evaluation_options.py --follow-imports=silent --ignore-missing-imports
```

定向 pytest 实际包含 16 个文件，完整参数见 JSON 的 `host-targeted-pytest`：evaluations/options/results/ws/auth、service_async、async_flow、results_service、result_iterations、workflow_contract、celery_app/tasks/config、task_submission_authorization、user_evaluation_concurrency 和 integration/test_api_workflows。其结果只证明这组回归通过；coverage 结论来自全量非 online 测试。

## 失败调查、警告与 skip

- **原 PR 的 mypy 环境阻塞已解除。** 本轮直接执行 issue 原命令，3 个源文件通过，exit 0；没有使用 `--python-version=3.12`，也不再用 `mypy src/` 代替 API 专项检查。[旧报告](https://github.com/JayNey/LLM-Algorithm-Harness/blob/545d62d46ef5c237731d9e57c9fddb7159665a0d/docs/frontend/EVALUATIONS_CHECKS.md)保留为历史证据。
- **本轮宿主 CI mypy 首次失败（exit 1，环境差异，已解除）。** 宿主缺少 `types-PyYAML`/`types-psutil`，且 mypy 2.3.1、SQLAlchemy 2.1.4、redis 6.4.0、Pydantic 2.13.5 与完整开发环境不同。5 个诊断为 `api/progress.py` 的 unused-ignore、`api/files/parsing.py` 的 SafeLoader/Any、成本服务的 2 个 var-annotated 和 1 个 generator 类型错误。保持源码与 pyproject 不变，在隔离 `.[dev]` 环境按同一 CI 命令复验，98 个源文件通过。该对照证明是环境依赖组合问题；不把每条错误未经单变量验证地归因于某一个包，也不把首次失败隐藏为通过。两轮输出均入库，无需代码豁免。
- 前端 lint 有 2 条既有 `BenchmarkDetailPage.tsx:131/145` 的 react-hooks/exhaustive-deps warning；build 有大于 500 kB 的 chunk 提示；均 exit 0。未调整阈值。
- 本轮证据文件引入的空白失败已修复：`git diff --check origin/main...e639932` 可复现日志一处尾随空格和末尾空行，exit 2。仅归一化日志格式、重算哈希后，对当前 HEAD 和工作区复验均 exit 0；该问题归类为本轮文档回归，不归为既有问题。
- 定向 Python 测试有 5 条既有 Pydantic class-based Config 弃用警告；全量 warning/skip 明细如下，不能把 skip 算作已验证。

全量合计 11 skips，按实际 SKIPPED 节点和 fixture 条件核对（完整节点名见日志）：

- Locust shape 检查 3 项：隔离 `.[dev]` 环境未安装可选 `.[performance]` 的 locust。
- `test_async_task_integration.py` 2 项：Redis broker 不可达；真实 Celery worker 未启动。
- `test_optional_online_leetcode_import` 1 项：`RUN_LEETCODE_ONLINE` 未设置。
- 容器监控 1 项：`MONITOR_CONTAINER_TESTS` 未设置。
- 队列监控 1 项：`MONITOR_QUEUE_TEST_BROKER` 未设置。
- Docker 沙箱 2 项：`RUN_DOCKER_TESTS` 未设置。
- `test_online_verification.py` 模块级 1 项：缺少供应商凭证，收集阶段跳过；没有发起真实模型调用。

128 条 warnings 主要为既有 Pydantic 配置、Pytest 对业务 TestCase/TestCaseResult 类的收集警告，以及依赖库弃用提示；全部原文见日志。总覆盖率 92.69%，并独立执行 src 和 api 双门禁。本地只验证 macOS/Python 3.11；CI 另装的 pylint/radon 不在本地隔离环境中，宿主 PATH 有 flake8，本地工具分支覆盖不等同 CI，平台矩阵按下方 CI 状态记录。

## 前置任务与代码／测试逐项核对

2026-10-27 读取 #216–#230 的公开正文、验收留言和关联 PR，15 项均 CLOSED。正文中的 2026-10-21 状态快照及未勾选框可能滞后，因此结合当前测试、已合并代码和后续公开验收记录判断；没有仅凭 issue 关闭推断行为通过。

- [#216](https://github.com/JayNey/LLM-Algorithm-Harness/issues/216)：`api/{evaluation_options,services/evaluation_options_service,routes/evaluation_options}.py` 和 `test_api_evaluation_options.py` 对应策略／来源、本人覆盖、排序分页、隐藏字段及两用户隔离；本轮定向和全量回归覆盖。
- [#217](https://github.com/JayNey/LLM-Algorithm-Harness/issues/217)：同一选项服务及测试中的 owned models、凭证替换重核、分页边界、timeout/close、脱敏和 complete 标记；使用 fake SDK，不宣称调用真实供应商。
- [#218](https://github.com/JayNey/LLM-Algorithm-Harness/issues/218)：`evaluation_service.py` 与 `test_evaluation_workflow_contract.py` 对应能力矩阵、两个 Session 的同 ID 启动竞争、CAS、发布失败可重试；ws/auth/async 回归覆盖。
- [#219](https://github.com/JayNey/LLM-Algorithm-Harness/issues/219)：schemas/service 的 execution_progress 与 workflow_contract、api_evaluations、api_ws、service_async 的状态／空单元／计数钳制断言；保留旧 progress。
- [#220](https://github.com/JayNey/LLM-Algorithm-Harness/issues/220)：`frontend/src/evaluations/{types,client,validation,presentation}` 与对应单测核对 URL、payload、signal、有限值、分页、未知状态和 nullable 指标；本轮 npm test 覆盖。
- [#221](https://github.com/JayNey/LLM-Algorithm-Harness/issues/221)：creation/session 与 creation.test 核对双提交互斥、未知创建结果、start 重试、身份与迟到响应隔离；全量前端单测及 #230 fixture 证据覆盖。
- [#222](https://github.com/JayNey/LLM-Algorithm-Harness/issues/222)：CreateEvaluationPage 与创建协调器；复核 [#230 的 all JSON](../superpowers/reports/assets/issue230/all/all.json) 中选项、预算、跨页选题、切换凭证、一次创建、错误重试与身份切换断言。
- [#223](https://github.com/JayNey/LLM-Algorithm-Harness/issues/223)：EvaluationsPage/useList 与 validation 单测；同一 all JSON 有分页、status、空页/超页收敛、503、旧响应不覆盖断言，未把请求失败当空页。
- [#224](https://github.com/JayNey/LLM-Algorithm-Harness/issues/224)：[PR #249](https://github.com/JayNey/LLM-Algorithm-Harness/pull/249) 的 EvaluationDetailPage/useEvaluation；all JSON 覆盖直接打开、权限拒绝、can_start/can_cancel、取消竞争、失败保留 ID、start 不重建。
- [#225](https://github.com/JayNey/LLM-Algorithm-Harness/issues/225)：[PR #256](https://github.com/JayNey/LLM-Algorithm-Harness/pull/256) 的 observer/useEvaluation；observer.test 覆盖 fake clock、退避、合并、权限和清理。早期留言待运行的 progress 场景由 #230 的 all JSON 补齐：HTTP 20%→事件失效→HTTP 60%、WS URL 无 token、周期不重叠；该证据是前置任务已执行记录，本轮未重跑浏览器。
- [#226](https://github.com/JayNey/LLM-Algorithm-Harness/issues/226)：ResultsPage/ResultDetailPage、results/client/presentation 单测及 all JSON，核对结果分页、跨页完整策略汇总、run_id=null、null 度量、未知成本与耗时单位。
- [#227](https://github.com/JayNey/LLM-Algorithm-Harness/issues/227)：[PR #280](https://github.com/JayNey/LLM-Algorithm-Harness/pull/280) 的 results/presentation/observer，核对任务状态×结果存在性、权限清缓存和终态单次补读；states fixture 已在 #230 all 验证。
- [#228](https://github.com/JayNey/LLM-Algorithm-Harness/issues/228)：[PR #278](https://github.com/JayNey/LLM-Algorithm-Harness/pull/278) 的 AppLayout/Navigation/MockActions、app-shell/notifications 单测；entries 和 shell 证据区分真实创建入口与 Mock 区域，保留 Frontier 外壳。
- [#229](https://github.com/JayNey/LLM-Algorithm-Harness/issues/229)：[PR #282](https://github.com/JayNey/LLM-Algorithm-Harness/pull/282) 已合并；[外观验收报告](../superpowers/reports/2026-10-27-evaluation-appearance-verify.md)及 #230 [appearance JSON](../superpowers/reports/assets/issue230/all/appearance/appearance.json) 记录 3 风格×2 主题×4 宽度、216 项断言及状态/键盘/无溢出检查。
- [#230](https://github.com/JayNey/LLM-Algorithm-Harness/issues/230)：[PR #291](https://github.com/JayNey/LLM-Algorithm-Harness/pull/291) 已合并，本轮 main 含完整离线 Cookie create/start/running/results/cancel、CSRF、两用户 404、并发 401/refresh、403、迟到 identity 回归。其 [验收报告](../superpowers/reports/2026-10-27-evaluation-auth-integration-verify.md)记录 HTTP199、browser all149+appearance216、security8、shell51；本轮定向/全量 HTTP 和前端单测覆盖合并后的实现。

上述 #234/#249/#256/#280/#278/#282/#291 的合并提交均已通过 `git merge-base --is-ancestor <merge_sha> HEAD` 核对为本轮基线祖先。#230 的 browser JSON 对应源码 `45d910fa92dd737ee562973fd24342d02ea50db4`；对应前端文件与本轮源码无改动，故作为继承证据引用，不冒充本轮执行。Browser all149、appearance216、security8 和 shell51 的 pass/断言及零未知请求/页面异常数据已再次读取核对。

## CI、检查范围与未验证层级

截至 2026-10-27 12:14（Asia/Shanghai），当前 main 的 [CI run 40444425429](https://github.com/JayNey/LLM-Algorithm-Harness/actions/runs/40444425429)（head=`b86d65eff2d2a76fdd39f54fe7b2794b9e3dc955`）有 8/10 jobs 通过，两个 Windows jobs 仍在运行（精确快照见 commands.json）。本地新分支尚未推送，不能宣称其新提交 CI 已通过。CI 的 Python 3.11/3.12 × Ubuntu/macOS/Windows 矩阵与本轮本地 macOS/Python 3.11 检查分别记录；既有 Security Check 中 bandit/safety 配有 continue-on-error，job 成功不等于安全扫描零发现。

- 本轮已执行：本地 Python 定向/全库非 online 测试、原始 API mypy、CI mypy、ruff/Black/编码检查，前端单测/lint/tsc/build。复核前置任务的离线 HTTP 和浏览器 fixture 证据。
- 浏览器 fixture 是真实 React/共享客户端配合拦截 HTTP/WS；本轮未重新启动浏览器。离线 HTTP 为真实 FastAPI/Cookie/CSRF/SQLite/worker 任务体，模型、沙箱和队列传输被替换。
- 真实 Redis/Celery 网络、供应商、Docker 沙箱和真实 browser↔API 的 Cookie/CORS/Set-Cookie 联调仍由 #232 跟踪；真实浏览器端到端、Windows 本机、Safari/Firefox、真机与屏幕阅读器不因本轮本地通过而被声明已验证。接口与交付汇总由 #233 跟踪。

## Issue #231 验收清单与审查

- [x] Step 1：定向 evaluations/results/ws/auth/service_async/celery/integration 和前端四项检查已执行，命令与退出码逐项记录。
- [x] Step 2：执行指定 ruff、全库 Black（覆盖改动 Python 文件；本轮无 Python 改动）及指定三个 API 文件的原始 mypy，未覆盖 Python 目标。
- [x] Step 3：全量非 online pytest、src≥90/api≥81、编码检查均通过；准确数量与 skip/警告在上方记录。
- [x] Step 4：逐项核对前置 issue、代码和测试；本轮 git diff --check 与平台/skip/警告记录在证据中。
- [x] Step 5（本地验证与材料）：失败分类及复验、代码 SHA、命令、退出码、覆盖范围及真实 CI 链接已记录；最终审查与远端交付状态如下。

材料自检通过：全部命令对应日志块哈希一致，14 项本地必需门禁退出码为 0；两个已解除的失败保留原始结果；源码与测试相对 main 无差异。最终集成审查在 Comet verify 阶段执行。GitHub issue/PR 尚未更新；#231 保持 OPEN，本地结果不自动等同远端交付。
