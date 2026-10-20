# Proposal: deploy-config（issue #159 部署配置与生产环境）

## Why

后端批次（#148–#159）只剩链尾 #159：平台已有完整的 FastAPI 应用、Celery 队列、Alembic 迁移和监控端点，但没有任何生产部署通道——无容器镜像、无完整编排、无反向代理、环境样例只有 4 个变量、依赖清单不区分开发/生产、部署文档缺失。没有这些，平台无法交付给真实用户运行。

## What Changes

- 新增 `Dockerfile.api` 与 `Dockerfile.worker`：多阶段构建、非 root 运行、内置健康检查；worker 镜像附带 docker CLI 供沙箱预检调用。
- `docker-compose.yml` 扩展为开发全栈（postgres/redis/api/worker/beat），保持现有 `redis` 服务名与健康检查不变，`scripts/run_integration_tests.sh` 的用法不受影响。
- 新增 `docker-compose.prod.yml`：生产编排（无源码挂载、`restart: unless-stopped`、nginx 入口、资源卷）。
- 新增 `deploy/nginx/nginx.conf`：gzip、API 限流、`/api/v1/ws` WebSocket 升级代理、HTTPS 部署注释模板。
- `.env.example` 从 4 个变量扩容为完整环境面（API/数据库/Redis/Celery/存储/沙箱/认证/日志），与 `api/config.py` 的 Settings 对齐。
- 依赖拆分：`requirements.txt` 收敛为运行时清单，新增 `requirements-dev.txt` 收拢开发工具（与 pyproject `[project.optional-dependencies].dev` 同步），并在文档中说明 pip-tools 锁定流程。
- 新增结构化日志配置：`LOG_LEVEL` / `LOG_FORMAT=json` 环境变量接入应用启动，生产默认 JSON 输出；Sentry/Prometheus 仅在文档中说明，不引入依赖（issue 标注可选）。
- 新增幂等种子数据脚本 `scripts/seed_data.py`（显式 UTF-8，跨平台），迁移回滚路径写入部署文档。
- 新增 `docs/deployment/deploy.md`：本地开发、Docker 部署、环境变量表、数据库迁移与回滚、故障排查。
- 新增 `tests/test_deployment_config.py`：以 YAML 解析与文本断言校验部署资产关键约束（非 root、健康检查、depends_on、WebSocket 升级、限流），不依赖 Docker 守护进程。

## Capabilities

### New Capabilities

- `deployment`：平台的生产部署能力——容器化交付、编排、反向代理、环境配置、结构化日志、迁移与种子数据。

### Modified Capabilities

- 无：本变更新增部署资产与配置项，不改变任何既有 spec 的需求行为。

## Impact

- 新文件：`Dockerfile.api`、`Dockerfile.worker`、`docker-compose.prod.yml`、`deploy/nginx/nginx.conf`、`requirements-dev.txt`、`scripts/seed_data.py`、`tests/test_deployment_config.py`、`docs/deployment/deploy.md`、`api/logging_config.py`。
- 修改文件：`docker-compose.yml`、`.env.example`、`requirements.txt`、`api/config.py`、`api/main.py`（日志装配接入点）、`README.md`（部署入口链接，如需要）。
- CI 影响：`ruff` / `black` / `find_missing_encoding` 覆盖新增 Python 文件；`pytest -m "not online"` 需保持全绿；`api/*` 覆盖率门禁（≥81%）不得被新增代码稀释。
- 兼容性：`docker compose up -d redis` 的既有用法保持可用；`requirements.txt` 仍可作为唯一运行时安装入口；不改动任何现有 API 行为。
- 明确不做：certbot 自动签发（文档给出模板）、前端静态资源托管（前端批次处理）、Sentry/Prometheus 接线（可选标注，仅文档）。
