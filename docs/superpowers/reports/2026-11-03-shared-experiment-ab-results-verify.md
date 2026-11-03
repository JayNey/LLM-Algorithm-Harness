# 验证报告：shared-experiment-ab-results

- 日期：2026-11-03
- Change：`shared-experiment-ab-results`
- 工作流：tweak
- 分支：`tweak/20261103/shared-experiment-ab-results`
- `verify_mode`：full（4 tasks / 30 changed files，均超过 light 阈值）
- `review_mode`：off。本 change 为部署路径与配置修复，任务级已覆盖新增分支与回归；按 tweak 默认跳过自动集成 code review，构建、测试、安全检查与 OpenSpec 校验仍全部执行。

## 规模与范围

`comet state scale` 结果：Tasks 4、delta specs 2 个文件（工具计 1 capability）、changed files 30，采用完整验证。

改动范围：新增共享结果根模块、实验/A/B 服务路径、API 与 worker 启动校验、两套 compose 结果卷、镜像目录授权、环境样例与部署文档，以及对应测试。

## 检查结果总览

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| tasks.md 全部完成 | PASS | 4/4 已勾选 |
| 实现符合 design.md 决策 | PASS | 下述决策映射 |
| Design Doc（`docs/superpowers/specs/`） | N/A | tweak 不产出独立 Design Doc；`design.md` 为本 change 的技术设计 |
| 能力规格场景覆盖 | PASS | 下表逐场景映射 |
| proposal 目标满足 | PASS | 结果/对比/面板/检查点跨进程可读且共享根可配置 |
| delta spec 与 design.md 无矛盾 | PASS | 路径、卷、启动校验、兼容策略一致 |
| 测试 | PASS | 245 passed（相关 8 文件）；58 passed（定向复跑） |
| 静态检查 | PASS | `ruff check .`、`black --check .` 通过；`mypy src/celery_app.py` 通过 |
| OpenSpec 校验 | PASS | `comet classic openspec -- validate ... --strict` |
| 安全 | PASS | 未引入密钥、路径穿越或新的 unsafe 操作 |

## 决策映射

1. `api/results.py` 提供 `results_root`、`ensure_results_root`、`resolve_results_path`；`Settings.RESULTS_ROOT` 与 `.env.example` 同步（`api/config.py:48-50`、`api/results.py:1-53`）。
2. 实验输出/检查点使用 `<root>/experiments/api/{id}/execution`（`api/services/experiment_service.py:281`、`:326`）；A/B 使用 `<root>/ab-tests/api/{id}/execution`（`api/services/ab_test_service.py:248`、`:303`）。
3. 读取路径兼容历史相对路径（`api/services/experiment_service.py:466`、`api/services/ab_test_service.py:386`）。
4. 启动校验：API lifespan（`api/main.py:81`）与 worker 入口（`src/celery_app.py:77-88`）。
5. 部署资产：镜像创建并授权 `results`；两套 compose 为 api/worker 挂载 `results_data:/app/results` 并声明命名卷（`docker-compose.yml`、`docker-compose.prod.yml`、`Dockerfile.api`、`Dockerfile.worker`）。
6. 文档：`docs/deployment/async-tasks.md`、`docs/deployment/deploy.md`、`.env.example`。

## 场景覆盖

| 场景 | 覆盖方式 | 证据 |
| --- | --- | --- |
| 分离进程读取实验结果 | `test_results_readable_from_another_working_directory` 切换 cwd 后请求 results/comparison/panel 均 200 | `tests/test_api_experiment_benchmark.py` |
| A/B 分离进程读取结果 | 同类测试在 A/B 生命周期后切换 cwd 请求结果 200 | `tests/test_api_experiment_benchmark.py` |
| 重启或换 Worker 后恢复 | 检查点固定到共享根；既有暂停/恢复测试验证同目录跳过已完成单元 | `tests/test_business_checkpoints.py:226-235`、`tests/test_business_checkpoints.py:255` |
| 结果根不可写 | 单元测试构造不可创建路径并断言 `RESULTS_ROOT is not writable`；启动路径调用该检查 | `tests/test_results_storage.py`、`api/main.py:81`、`src/celery_app.py:88` |
| 非 root 用户可写结果目录 | 镜像 `mkdir -p ... results` + `chown`，部署测试断言 | `tests/test_deployment_config.py` |
| 结果卷跨服务共享 | 两套 compose 均断言 `results_data:/app/results` 与顶层卷 | `tests/test_deployment_config.py` |
| 环境样例覆盖 `RESULTS_ROOT` | 既有 Settings 字段防漂移测试 | `tests/test_deployment_config.py::TestEnvExample` |

## 执行记录

```bash
python3 -m pytest tests/test_results_storage.py tests/test_deployment_config.py \
  tests/test_api_experiment_benchmark.py tests/test_experiment_task.py \
  tests/test_ab_test_task.py tests/test_experiment_cancellation.py \
  tests/test_experiment_queue_safety.py tests/test_api_restart_worker_recovery.py -q --no-cov
# 245 passed

python3 -m pytest tests/test_results_storage.py tests/test_deployment_config.py \
  tests/test_api_experiment_benchmark.py::TestExperiments::test_results_readable_from_another_working_directory \
  tests/test_api_experiment_benchmark.py::TestABTests::test_results_readable_from_another_working_directory \
  tests/test_business_checkpoints.py -q --no-cov
# 58 passed

ruff check .            # All checks passed
black --check .         # 380 files would be left unchanged
mypy src/celery_app.py --ignore-missing-imports   # Success
comet classic openspec -- validate shared-experiment-ab-results --type change --strict --no-interactive
# Change 'shared-experiment-ab-results' is valid
```

`mypy src/ --ignore-missing-imports` 会跟随导入检查 `api/`，仍报告 4 个与本 change 文件无关的既有错误（`api/files/parsing.py`、`api/progress.py`、`api/services/cost_alert_service.py`）；本 change 新增/修改文件无新增类型错误。

## 问题

### CRITICAL

无。

### WARNING

无。

### SUGGESTION

- 基准运行检查点仍使用相对 `results/benchmarks/api/{run_id}/units`；compose 的 `/app/results` 卷与同一 cwd 约定可覆盖，但不随 `RESULTS_ROOT` 变化。本 change 范围限定实验/A/B，若后续统一可在基准服务复用 `results_root()`。

## 结论

无 CRITICAL/WARNING 问题，任务全部完成，能力场景有实现与测试映射；验证通过，可进入归档前确认。`branch_status` 保持 `pending`，等待 `/comet-archive` 的最终确认。
