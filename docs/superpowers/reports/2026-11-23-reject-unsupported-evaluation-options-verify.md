# 验证报告：reject-unsupported-evaluation-options

日期：2026-11-23。基线：`6668006d011bd6481b84f4145551b7f48439b630`。工作区：`/Users/verstappen/LLM-Algorithm-Harness`，验证时分支 `main`，交付分支 `codex/reject-unsupported-evaluation-options`。

## 结论与范围

本次已批准的“明确拒绝未实现配置”修复通过目标验收。共 4/4 项任务、3/3 条新增需求、6/6 个规格场景完成核对；未发现本 change 的 CRITICAL、IMPORTANT、WARNING 或 SUGGESTION 问题。未将本结论扩大为全仓测试全部通过。

| 维度 | 结果 |
| --- | --- |
| 完整性 | 4/4 tasks；3/3 新增需求具备实现与文档，未新增或修改数据库字段 |
| 正确性 | 6/6 场景覆盖；真实 HTTP、持久化、副作用与真实 worker 配置均有执行证据 |
| 一致性 | 与已批准的拒绝方案一致，沿用字段校验器和既有错误中间件；未启用并行或更改沙箱时限 |
| 独立审查 | 不适用：本 Run 配置 `direct/direct/off`，当前 Agent 自查不视为独立审查 |

六个交付文件为 `api/models.py`、`api/documentation.py`、`API.md`、`docs/api-versioning.md`、`tests/integration/test_api_workflows.py`、`tests/fixtures/openapi-v1.json`。测试集中放入真实工作流测试文件；为修正公开 PATCH 示例，修改了提供该示例的 `api/documentation.py`，无需修改原预计的 `tests/test_api_evaluations.py`。文件总数、范围与风险保持在已批准提案内。

## 规格与实现映射

| 场景 | 实现与验证证据 |
| --- | --- |
| 拒绝 Issue 的自定义参数 | `api/models.py:47` 的 before 字段校验；`tests/integration/test_api_workflows.py:230` 覆盖普通、with-selection 与 with-dataset-version 三个真实 HTTP 入口、单字段与组合；响应 400，Evaluation/AsyncTask 无新增，队列为空 |
| 历史默认值与 null | 同一 HTTP 参数矩阵包含 timeout=300、concurrency=5、两字段 null，以及字符串与布尔值；统一拒绝并定位字段 |
| PATCH 超时不再静默成功 | `api/models.py:116`；`tests/integration/test_api_workflows.py:263` 比较更新前后整条数据库记录，连带 budget_cap_usd=2 的修改也不生效，且无任务发布 |
| 公开说明与迁移 | 字段描述明确不支持与占位默认值，三个请求组件共五个字段标记弃用；模型与公开 PATCH 示例移除无效参数；API.md 和版本文档说明迁移及兼容影响；原有文档示例验证与严格 OpenAPI 门禁通过 |
| 省略字段后 worker 配置一致 | `tests/integration/test_api_workflows.py:313` 从 HTTP 创建、持久化、预算 PATCH、启动到真实 Celery task body 和 TaskService；实际 max_workers=1，SandboxExecutor 读取 timeout=5，结果 completed |
| 独立生成超时仍有效 | 同一真实 worker 测试持久化 generation_timeout_seconds=18，并在真实策略生成路径观察到模型超时为 18 秒预算内，明显区别于 5 秒沙箱时限；原有生成超时 API 测试同时通过 |

异步创建是 `EvaluationService.create_evaluation_async` 服务方法，没有独立的异步创建 HTTP 端点。新增服务请求检查验证同一请求模型在进入该方法前拒绝参数，数据库与队列没有副作用；真实公开异步启动路径由合法 HTTP 创建后启动的链路测试及已有 generic submission 测试覆盖。没有将只测 schema 当作整个链路证据。

沿用现有错误中间件的校验错误结构：HTTP 400，`error.code=INVALID_PARAMETER`，`details` 按字段定位。规格中的 validation_error 表示请求校验失败，不引入新的错误枚举或改变既有错误契约。

## 实际检查

所有命令均从上述工作区执行，除非另有说明。

1. 先运行新增 HTTP 拒绝回归，前三个用例在未实现校验时因实际返回 **201 而非 400** 失败，确认能捕获 Issue 原问题；实现后新增检查 **37 passed**。日志 `/private/tmp/issue513-green.log`。
2. 相关回归命令：

   ```text
   .venv/bin/python -m pytest tests/test_api_evaluations.py tests/integration/test_api_workflows.py tests/test_api_versioning.py tests/test_api_documentation.py tests/test_evaluation_service_async.py tests/test_generic_evaluation_submission.py tests/unit/test_api_endpoints.py -o addopts= -q
   ```

   结果 **1113 passed, 40 warnings**；新增 37 项包含在此总数内，不重复累计。日志 `/private/tmp/issue513-regression.log`。
3. Black `--check` 与 Ruff `check`：对三个修改的 Python 文件执行，通过。
4. `.venv/bin/python -m mypy api/models.py`：通过。扩大到 `api/documentation.py` 时的既有问题见下一节，未伪报该模块类型检查通过。
5. `comet classic openspec -- validate reject-unsupported-evaluation-options --strict`：通过；当前 tasks 为 4/4。
6. `git diff --check`：通过。
7. 额外解析 HEAD 与当前 OpenAPI 基线，移除两组件三处新增弃用标记后 JSON 完全相等；只定向增加三个标记，没有重录或放宽门禁。派生的个人集合版本请求尚未纳入旧冻结基线，实际 schema 和真实 HTTP 已覆盖。

## 扩大检查的真实结果与限制

已尝试 `.venv/bin/python -m pytest -m 'not online' -o addopts= -q --maxfail=10`。本轮出现四个准备阶段错误后中断，未完成全仓检查；退出时还产生 pytest tmp_path teardown 的 KeyboardInterrupt/KeyError。该次全仓命令不计为通过。日志 `/private/tmp/issue513-offline-suite.log`。

四个错误单独复现，全部由 `tests/test_api_cost.py:631` 绑定 `127.0.0.1` 端口时的沙箱 `PermissionError` 引起：

- `TestPricing::test_full_model_ids_round_trip_over_http`
- `TestPricing::test_full_model_id_auth_and_validation_over_http`
- `test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]`
- `test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[ab]`

允许本地 HTTP 端口后对同四项复测，结果 **4 passed, 9 warnings**；提供商仍为测试替身。原错误日志 `/private/tmp/issue513-broader-errors.log`，复测日志 `/private/tmp/issue513-broader-recheck.log`。没有重跑整个全仓命令，也不声称其余未完成部分通过。

扩大类型检查得到三个错误：`api/documentation.py:63` JOB 缺少注解、`:1928` object 无 items 属性、`:2038` 不能赋值给方法。把未修改的 HEAD 原文复制到系统临时目录并独立运行相同 mypy 后，得到相同三个错误与行号；该模块此次只改 PATCH 示例字典中的一个键值。基线日志 `/private/tmp/issue513-mypy-baseline.log`。这是现有基线限制，未在本 change 中修复；模型文件的必要类型检查通过。

没有进行真实付费模型调用、生产修改或完整外部服务集成验证。现有 Pydantic、datetime 与 pytest-asyncio 弃用警告保留记录。上述扩大检查限制不改变本次目标验收及风险结论。

## 兼容影响与交付状态

显式发送旧字段的客户端需删除字段；这一 v1 行为收紧已在 Open 提案中明确展示，并经用户“确认”批准。省略字段的调用继续运行，独立模型生成超时仍按原契约持久化与使用。

用户后续明确授权“归档并推送、创建pr”。交付目标为 `origin/codex/reject-unsupported-evaluation-options`，向 `JayNey/LLM-Algorithm-Harness` 的 `main` 创建 PR，关联 Issue #513。功能分支与原验证基线及已更新的 origin/main 相同；仅刷新交付绑定与报告说明，复用全部有效实现检查。归档、Git 提交、推送及 PR 的实际完成由同一 Run 的交付收据核对。
