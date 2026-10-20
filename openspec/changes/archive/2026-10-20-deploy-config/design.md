# Design: deploy-config

> 流程确认（2026-10-20）：预计改动约 14 个文件，超过 tweak 提示阈值（>6）。经用户确认继续 tweak 轻量流程——理由：无跨模块架构协调、无新公共 API、无数据库 schema 变更，改动以配置/文档资产为主，逻辑代码仅日志装配与种子脚本且均配套单测。

## 现状盘点（上游 main ab0497e）

已存在、本 change 不重复建设：

- **Alembic 迁移**：`api/db/migrate.py` 提供编程式入口（启动时 `run_migrations`），`api/db/migrations/versions/` 已有 5 个版本；回滚用 `downgrade()`。无需 alembic.ini。
- **健康/监控端点**：`api/main.py` 有 `/api/v1/health`；`api/routes/monitoring.py` 有 `/health/database`、`/health/redis`、`/health/workers`、`/health/sandbox`、`/system/status` 等。
- **Celery**：`src/celery_app.py` 已配置队列路由与 beat 定时任务（每天 2/3 点）；`scripts/start_worker.sh` 存在。
- **配置基座**：`api/config.py` 用 pydantic-settings（`.env` 支持，`extra=ignore`）；`DATABASE_URL`（None 回退 SQLite，生产指 PostgreSQL）、`CELERY_BROKER_URL` 等已定义。
- **依赖基座**：pyproject 为 PEP 621（setuptools），`[project].dependencies` 运行时 + `[project.optional-dependencies].dev`；`requirements.txt` 为手工清单（运行时+开发混装）。

## 关键决策

1. **compose 布局**：`docker-compose.yml` 原样保留 `redis` 服务的名称、端口与健康检查（`scripts/run_integration_tests.sh` 和 CI 依赖 `docker compose up -d redis`），在此文件上扩展开发全栈（postgres/api/worker/beat，api/worker 用 build + 源码挂载便于热更）。生产编排放独立的 `docker-compose.prod.yml`（镜像构建、无源码挂载、`restart: unless-stopped`、卷化数据）。两个文件通过 `-f` 显式选择，不用 overlay 叠加，避免隐式合并踩坑。
2. **镜像**：基础 `python:3.11-slim`；多阶段（builder 阶段 `pip install --prefix` 装依赖，runtime 阶段拷贝 venv 与源码）；非 root 用户 `harness`；`HEALTHCHECK` 用 `python -c urllib`（slim 镜像无 curl）；`ENTRYPOINT` 分别为 uvicorn 与 celery worker。worker 镜像加装 `docker-cli` 包（沙箱预检要调用宿主 docker，daemon 仍来自 compose 挂载的 `/var/run/docker.sock`，仅生产编排显式挂载并注释安全影响）。
3. **日志**：新增 `api/logging_config.py`，按 `LOG_FORMAT`（`json`|`text`）装配 structlog 渲染器与 uvicorn/根日志 handler，`LOG_LEVEL` 控制级别；`api/main.py` 的 lifespan 启动时调用一次。`api/config.py` 增加两个字段（默认 `INFO`/`text`，生产行为由 compose 环境注入 `json`）。不引新依赖（structlog 已在依赖中）。
4. **依赖拆分**：`requirements.txt` 只留运行时（对齐 `[project].dependencies` 的 API 相关子集 + 现有 CLI/报告依赖），开发工具移入 `requirements-dev.txt`（对齐 dev extras）。两份清单与 pyproject 的同步关系写入部署文档；锁定流程文档化（`pip-compile requirements.in` 由使用者按环境生成，仓库不提交解析产物，避免与 CI 网络解析耦合）。
5. **种子数据**：`scripts/seed_data.py` 复用 `api/db` 的模型与会话（engine 初始化 + `run_migrations`），幂等导入最小示例题目集；所有文件 I/O 显式 `encoding="utf-8"`（CI 有 `find_missing_encoding.py` 门禁）。
6. **nginx**：`deploy/nginx/nginx.conf`——上游 `api:8000`；`/api/v1/ws` 加 `Upgrade`/`Connection` 头；`limit_req` 按 IP 限流 API；gzip 开启；`client_max_body_size` 对齐上传上限；HTTPS server 块以注释模板给出（证书路径 + 301 跳转），不默认启用。
7. **测试策略（无 Docker 依赖）**：`tests/test_deployment_config.py` 用 `yaml.safe_load` 解析两个 compose 文件与文本断言校验：api/worker 服务存在且 depends_on 正确、prod 无源码挂载且 restart 策略就位、Dockerfile 含 `USER harness` 与 `HEALTHCHECK`、nginx.conf 含 ws 升级头与 `limit_req`、`.env.example` 覆盖 Settings 全部字段（导入 Settings 对比，防漂移）。logging/seed 走常规单测（tmp path + SQLite）。

## 风险与回退

- **CI 兼容**：不动 CI 工作流；`requirements.txt` 拆分后 CI 若直接 `pip install -r requirements.txt` 仍成立（运行时清单自足）。实施时核对 ci.yml 的安装命令后再动手。
- **覆盖率门禁**：新增 `api/logging_config.py` 与 `scripts/seed_data.py` 计入 `api/*`/全库门禁，配套单测保证不稀释。
- **回退**：全部为新增资产 + 少量加字段，回退即删文件/还原字段；无数据迁移、无 API 行为变化。
