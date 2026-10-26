# 真实评估工程质量检查矩阵（#231 / T16）

执行日期：2026-10-26　基线：`main`@`c853bda`（#278 合并提交）　分支：`tweak/20261026/evaluation-quality-gates`

**口径**：校验门槛以执行时 main 的 CI 配置（`.github/workflows/ci.yml`）为准；本变更零代码改动，仅执行与记录。

**执行环境**：macOS 15.8.1（arm64）、Python 3.14.3、Node v26.0.0 / npm 11.12.1；pytest 9.1.1、ruff 0.17.0、black 26.10.1、mypy 2.3.1、coverage 7.16.1。

## 检查矩阵

| 检查 | 命令 | 结果 | 退出码 |
|---|---|---|---|
| 前端单测 | `npm test`（frontend/） | 256 passed / 0 failed | 0 |
| 前端 lint | `npm run lint` | 0 errors，2 warnings（既有，见下） | 0 |
| 前端类型 | `npx tsc -b` | 干净 | 0 |
| 前端构建 | `npm run build` | ✓ built in 1.03s | 0 |
| ruff（issue 范围） | `ruff check api/ tests/test_api_evaluation_options.py tests/test_evaluation_workflow_contract.py tests/integration/test_api_workflows.py` | All checks passed | 0 |
| ruff（CI 全库） | `ruff check .` | All checks passed | 0 |
| black（CI 全库） | `black --check .` | 347 files unchanged | 0 |
| 编码检查 | `python3 scripts/find_missing_encoding.py` | Implicit text encodings: 0 | 0 |
| 全量测试（CI 同命令） | `python3 -m pytest -m "not online"` | **3252 passed / 25 skipped / 0 failed**，1937 warnings，6m50s | 0 |
| 覆盖率门禁 src | `python3 -m coverage report --include="src/*" --fail-under=90` | **90.95%** ≥ 90 | 0 |
| 覆盖率门禁 api | `python3 -m coverage report --include="api/*" --fail-under=81` | **94.35%** ≥ 81 | 0 |
| 定向测试 | `pytest tests/test_api_{evaluation_options,evaluations,evaluation_results,ws,auth}.py tests/test_evaluation_{service_async,async_flow,results_service,result_iterations,workflow_contract}.py tests/test_{celery_app,celery_tasks,config_celery,task_submission_authorization,user_evaluation_concurrency}.py tests/integration/test_api_workflows.py --no-cov -q` | **353 passed / 0 failed**（84.7s） | 0 |

pytest 内置 `--cov-fail-under=90`（pyproject addopts）在全量运行中同步通过（TOTAL 92.22%）。

## mypy 的环境阻塞与处置

issue 基线命令 `mypy api/evaluation_options.py api/services/evaluation_options_service.py api/routes/evaluation_options.py --follow-imports=silent --ignore-missing-imports` 在本机 **exit 2**：

```
numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater [syntax]
```

- **归类：环境阻塞，非代码问题。** pyproject `[tool.mypy] python_version = "3.10"`，而本机 Python 3.14.3 环境安装的 numpy 2.x 类型桩使用 3.12+ 的 `type` 语句，在 3.10 目标下无法解析；错误位于第三方 `.pyi`，不在仓库代码。
- **处置**：同命令追加 `--python-version=3.12` 后 **Success: no issues found in 3 source files**（exit 0）。
- **CI 层级证据**：CI Type Check job（Python 3.11 + `pip install -e ".[dev]"`，`mypy src/ --ignore-missing-imports`）在本基线 SHA 上通过（[run 40259311396](https://github.com/JayNey/LLM-Algorithm-Harness/actions/runs/40259311396)，1m14s，10/10 全绿，含 Windows 矩阵）。

## 失败 / 警告分类（既有项，非本次引入）

本次变更零代码改动，**无新增回归**。

| 项 | 归类 | 明细 |
|---|---|---|
| eslint 2 warnings | 既有警告 | `BenchmarkDetailPage.tsx:131/145` react-hooks/exhaustive-deps（`runFinished` 多余依赖） |
| pytest 1937 warnings | 既有警告 | 主要为 `datetime.utcnow()` DeprecationWarning 等弃用提示 |
| 全量 25 skipped | 外部依赖 skip | 依赖外部服务的用例按既有标记跳过 |
| mypy `src/` 3.12 覆盖 5 errors | 既有（目标版本差异） | 4× unused-ignore（`src/importers/leetcode.py:50/203/292`、`src/importers/codeforces.py:15`）、1× arg-type（`api/services/evaluation_results_service.py:764`）。仅在使用 `--python-version=3.12` 覆盖时出现；CI 的 3.11 运行时 + 3.10 目标组合下不存在（CI 绿），**不修改**——按 3.12 口径改 type: ignore 反而可能破坏 CI 口径（unused-ignore 随目标版本翻转） |

## 与 issue 基线命令的差异说明

- mypy 原命令受上述环境阻塞，以「`--python-version=3.12` 覆盖本地通过 + CI 同 SHA 绿」双证据替代；未降低任何门槛。
- 定向测试为控制时长使用 `--no-cov -q`（覆盖率结论以全量 CI 同命令运行为准，两者分开记录）。
- 其余命令均与 issue/CI 原文逐字一致。

## 验证层级与未验证项

- **已验证**：本地单测/集成离线层级（fixture、离线 HTTP、内存 Celery 任务）、CI 对应全量门禁、前端四件套。
- **未在本任务执行**：真实 Redis/Celery broker、真实模型供应商与沙箱联调、真实浏览器端到端——属 #232（T17）层级；接口文档与验收证据汇总属 #233（T18）。
