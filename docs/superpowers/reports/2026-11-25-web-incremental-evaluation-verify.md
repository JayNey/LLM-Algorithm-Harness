# Web 增量评估验收报告

- Change：`web-incremental-evaluation`；Issue：[#475](https://github.com/JayNey/LLM-Algorithm-Harness/issues/475)。
- 基线：`58d6b9770005f357ccec68fc207be34024c2bf3d`；工作区：初次验收在当前目录 `main`，用户选择 PR 后迁移到 `codex/web-incremental-evaluation`。仅分支和交付记录改变，实现输入未变，沿用本报告的有效检查结果。
- 用户明确选择方案 2，批准完整范围继续 tweak；Runtime 已保存 `continue` 决定。配置：direct / direct / review off。
- 结论：12/12 任务完成，10 个需求和 25 个场景已核对；无 CRITICAL、IMPORTANT、WARNING 或待接受偏差。独立审查按已确认配置不适用。

## 结果

创建页可选择复用本人历史并预览题目 × 策略计数；提交固定完整题目、配置、来源与结果副本。worker 物化复用单元，只运行剩余单元，全部复用不初始化模型/沙箱运行时。原始统计与本次新增费用分别保存，暂停恢复和重投递保持幂等。API 1.9.0 只增加可选字段与预览操作，已定向更新兼容性基线。

## 规格核对

| 需求 | 场景数 | 实现与验证证据 |
| --- | ---: | --- |
| 评估单元真实执行 | 3 | `src/tasks/evaluation.py` 保留真实 worker，兼容单元跳过；原有真实执行回归及全复用零调用测试 |
| 本人历史单元复用预览 | 3 | `api/services/evaluation_reuse.py` 按 owner、指纹和有效执行筛选；混合 3 题 × 2 策略、模型/策略/超时/测试变化、跨用户/取消/未执行/旧信息测试 |
| 增量提交固定题目和复用计划 | 3 | 业务库私有 JSON 保存题目、配置、来源与副本；HTTP 普通/选题/集合版本创建、个人题覆盖与来源删除、暂停改题测试 |
| 复用费用与新增调用费用隔离 | 2 | `new_cost_usd/new_cost_unknown` 与原始度量分离；混合费用、零预算且无定价全复用、历史未知成本测试 |
| 增量计划恢复与结果幂等 | 2 | 原执行独占、检查点及 SQL 幂等键；暂停恢复、file/SQL 提交窗口、重复投递和损坏计划拒绝测试 |
| 复用结果来源与运行汇总 | 2 | 结果详情返回来源与整次计划汇总；分页、来源删除及原始 token/成本保留测试 |
| 结果统计区分原始成本和新增费用 | 3 | JSON、Markdown、HTML 与增量 CSV 明确成本口径；历史未知费用、全复用、他人读取拒绝与新增未知费用显示 null 测试 |
| 创建评估时选择复用并预览 | 2 | 开关默认关闭；预览成功/失败/重试与零命中逻辑、浏览器实际交互 |
| 预览与当前草稿和账号一致 | 3 | creation store 使用 AbortController 与请求纪元；乱序、草稿变化、账号切换和最终提交数量测试 |
| 结果页展示复用来源和新增成本 | 2 | 来源链接、复用/新跑计数、原始/新增成本、真实 success 状态文案；浏览器与后端恢复测试 |

题目指纹另外运行 12 个字段场景，覆盖题目内容、入口、三类测试及判题配置。新跑结果保存兼容指纹；缺少证据的旧结果、动态 few-shot 示例池及非实际执行结果保守新跑。

## 实际检查

所有命令均在本仓库执行，前端命令工作目录为 `frontend`。日志与 checks JSON 位于当前 change 的 `.comet/checks/` 和 `.comet/checks.json`，归档时随 change 保存。

| 检查 | 实际结果 | 日志 |
| --- | --- | --- |
| 16 个相关后端模块 | **597 passed** | `backend.log` |
| 结果费用补充回归 | **32 passed** | `cost-view.log` |
| 题目指纹字段专项 | **12 passed** | `fingerprint-fields.log` |
| 全复用、零预算、无定价专项 | **1 passed**，禁止构造运行时 | `zero-budget-no-pricing.log` |
| `npm test` | **370 passed** | `frontend-tests.log` |
| `npm run build` / `npm run lint` | 均通过 | `frontend-build.log` / `frontend-lint.log` |
| Ruff / Black | Ruff 通过，Black 检查的 16 个文件无需修改 | `python-lint.log` 与平台检查输出 |
| 定向 mypy | 8 个源码文件无问题 | `python-types.log` |
| 生产构建浏览器检查 | 预览、失败重试、选题刷新、提交、来源与 320/390/1280px 布局通过，无 pageerror | `browser.log` 与 assets 中的 `report.json` |
| OpenSpec 严格校验 / `git diff --check` | 通过 | 平台检查输出 |

后端完整命令：

```bash
.venv/bin/python -m pytest \
  tests/test_celery_tasks.py tests/test_api_evaluation_reuse.py \
  tests/test_api_evaluations.py tests/test_api_evaluation_options.py \
  tests/test_evaluation_workflow_contract.py tests/test_evaluation_service_async.py \
  tests/test_evaluation_results_service.py tests/test_api_evaluation_results.py \
  tests/test_evaluation_artifacts.py tests/test_budget_coverage.py \
  tests/test_spend_execution.py tests/test_web_cost_alerts.py \
  tests/test_api_versioning.py tests/test_api_documentation.py \
  tests/test_evaluation_async_flow.py tests/test_api_restart_worker_recovery.py \
  --no-cov -q
```

类型检查使用 `mypy --follow-imports=silent --ignore-missing-imports` 检查 `evaluation_reuse`、评估服务/结果/产物/费用/告警、评估路由与 worker。未过滤依赖的全图检查存在仓库已有的缺少第三方类型存根等错误；没有修改或掩盖仓库的 mypy 配置。

## 验证边界与处理

- 全部模型响应使用离线受控替身，未调用真实付费供应商。真实任务生命周期、数据库、检查点、指纹、费用差量与 HTTP 鉴权路径参与后端测试。
- 浏览器使用真实生产构建、React、router、客户端和 creation store，HTTP 为离线 fixture。分析面板的四个接口故意返回 404，验证其错误隔离；浏览器证据不作为真实供应商或分析接口 E2E 结论。
- 已检查 SQLite 迁移升级/回退和旧记录默认值，生成 PostgreSQL SQL；未连接真实 PostgreSQL 服务。
- 初次相关回归的失败已定位并修复；本机端口限制通过允许本地端口的最终完整运行消除。最终完整运行 597 项全部通过。
- 当前代码、需求和设计保持同一批准范围。文件数量超过 6 的范围复核已获明确批准，未静默缩减验收或切换 workflow。

## 界面证据

- [创建页](assets/web-incremental-evaluation/create-desktop.png)
- [桌面结果页](assets/web-incremental-evaluation/results-1280.png)
- [390px 结果页](assets/web-incremental-evaluation/results-390.png)
- [浏览器回执](assets/web-incremental-evaluation/report.json)

本报告完成规格一致性与风险核对。Comet Verify 守卫通过后进入 Archive，归档和 Git 交付仍等待用户选择。
