## Why

实验/A/B 的结果、对比/面板和检查点仍写在运行进程的相对 `results/` 目录中，而开发与生产 compose 的 api、worker 并未共享该目录，镜像也没有创建并授权 `/app/results`。因此 worker 完成任务后，API 容器读取 `output_dir` 会报 `artifacts are missing`；worker 重启或多副本后，暂停任务也找不到检查点（见 `docs/reviews/2026-11-03-frontend-backend-completion-review.md` P0-2）。评估结果已经落库，实验/A/B 仍停留在 worker 本地文件系统。

## What Changes

- 引入可配置的 `RESULTS_ROOT`（默认仓库根 `results/`，随 `.env.example` 提供），实验与 A/B 的输出目录和检查点统一解析到该根下的绝对路径。
- 结果摘要、对比报告与面板在读取时基于同一 `RESULTS_ROOT` 解析，并兼容历史相对路径，不再依赖 API 进程的当前工作目录。
- API 与 worker 启动时校验 `RESULTS_ROOT` 可创建且可写，失败立即给出明确错误，而不是等到首个任务写文件时才失败。
- `Dockerfile.api`、`Dockerfile.worker` 创建 `/app/results` 并以 `harness` 用户授权。
- 开发与生产 compose 的 api、worker 都挂载同一命名卷 `results_data:/app/results`。
- 部署文档与目录说明同步为共享结果卷 + `RESULTS_ROOT`。

非目标：不改执行、定价、进度或完整性语义；不迁移历史产物到新位置；不引入对象存储或数据库结果快照；不改前端与 API 响应结构。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/experiment-management`: 实验结果、对比/面板和 A/B 结果从跨进程共享且可配置的产物根读取；检查点随共享卷持久化，重启或换 worker 后可继续。
- `deployment`: compose 必须为 api 与 worker 提供同一结果卷，镜像必须创建可写的 `results` 目录，环境样例必须覆盖 `RESULTS_ROOT`，启动时校验其可写性。

## Impact

涉及 `api/config.py` 或新增结果根模块、`api/services/experiment_service.py`、`api/services/ab_test_service.py`、`api/main.py`、`src/celery_app.py`、`Dockerfile.api`、`Dockerfile.worker`、`docker-compose.yml`、`docker-compose.prod.yml`、`.env.example`、`docs/deployment/*` 与相关测试。不改变数据库结构和既有 API 契约。
