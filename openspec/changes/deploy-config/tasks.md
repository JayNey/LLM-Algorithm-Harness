# Tasks: deploy-config

## 1. 依赖与环境

- [x] 1.1 拆分依赖清单：`requirements.txt` 收敛为运行时清单，新增 `requirements-dev.txt`（对齐 pyproject dev extras），核对 ci.yml 安装命令不受影响
- [x] 1.2 扩容 `.env.example`：覆盖 `api/config.py` Settings 全部字段并按 API/数据库/Redis/Celery/存储/沙箱/认证/日志分组注释
- [x] 1.3 `api/config.py` 增加 `LOG_LEVEL` / `LOG_FORMAT` 字段；新增 `api/logging_config.py` 按 `LOG_FORMAT`（json|text）装配 structlog + uvicorn 日志（含单测）

## 2. 容器化

- [x] 2.1 新增 `Dockerfile.api`：多阶段构建、非 root 用户 `harness`、`HEALTHCHECK` 指向 `/api/v1/health`、uvicorn 入口
- [x] 2.2 新增 `Dockerfile.worker`：celery worker 入口、附带 docker CLI 供沙箱预检、非 root 运行
- [x] 2.3 `docker-compose.yml` 扩展为开发全栈（postgres/api/worker/beat），保持 `redis` 服务名/端口/健康检查不变以兼容 `scripts/run_integration_tests.sh`
- [x] 2.4 新增 `docker-compose.prod.yml`：postgres/redis/api/worker/beat/nginx、`restart: unless-stopped`、数据卷、无源码挂载、`LOG_FORMAT=json`

## 3. 反向代理

- [x] 3.1 新增 `deploy/nginx/nginx.conf`：上游 `api:8000`、gzip、`limit_req` API 限流、`/api/v1/ws` WebSocket 升级代理、`client_max_body_size` 对齐上传上限、HTTPS 注释模板

## 4. 数据与脚本

- [x] 4.1 新增 `scripts/seed_data.py`：幂等导入最小示例题目集（engine 初始化 + `run_migrations` + 显式 UTF-8），含单测（tmp SQLite 验证重复执行不重复插入）

## 5. 测试与文档

- [x] 5.1 新增 `tests/test_deployment_config.py`：YAML/文本断言校验 compose×2、Dockerfile×2、nginx、`.env.example` 与 Settings 字段一致性（不依赖 Docker 守护进程）
- [x] 5.2 新增 `docs/deployment/deploy.md`：本地开发、Docker 部署（dev/prod）、环境变量表、数据库迁移与回滚步骤、种子数据、故障排查
- [ ] 5.3 独立审查（general-purpose 只读子代理，`git show` 范围 + 已知豁免清单），修复后定点复审
- [ ] 5.4 三件套最终重验：`ruff check --fix .` + `black .` 后在最终状态重跑 `ruff check .`、`black --check .`、`python3 -m pytest -q --cov-fail-under=0`（覆盖率门禁豁免口径见验证记录）
