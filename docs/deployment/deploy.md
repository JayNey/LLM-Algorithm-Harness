# 部署指南（issue #159）

本指南覆盖本地开发、Docker 部署（开发/生产）、环境变量、数据库迁移与故障排查。
部署资产清单：`Dockerfile.api`、`Dockerfile.worker`、`docker-compose.yml`（开发）、
`docker-compose.prod.yml`（生产）、`deploy/nginx/nginx.conf`、`.env.example`、
`scripts/seed_data.py`。

## 1. 本地开发（不用 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # 运行时依赖
pip install -r requirements-dev.txt        # 开发/测试工具（CI 用 `pip install -e ".[dev]"`）
cp .env.example .env                       # 填写 SECRET_KEY / ENCRYPTION_KEY 后再启动

python3 -m uvicorn api.main:app --reload   # API，默认 http://localhost:8000
celery -A src.celery_app worker --loglevel=INFO   # 异步评估 worker（可选）
celery -A src.celery_app beat --loglevel=INFO     # 定时任务（可选）
```

不配置 `DATABASE_URL` 时业务库回退到本地 SQLite（`data/business/business.sqlite3`）；
Celery 相关功能需要 Redis（`docker compose up -d redis` 或本地 Redis）。

### 依赖锁定（可复现部署）

仓库清单只含下限约束。需要精确锁定时用 pip-tools 在目标环境生成锁文件：

```bash
pip install pip-tools
pip-compile requirements.txt      --output-file requirements.lock
pip-compile requirements-dev.txt  --output-file requirements-dev.lock
pip install -r requirements.lock
```

锁文件由各部署方自行保管，仓库不提交解析结果。`requirements.txt` /
`requirements-dev.txt` 与 `pyproject.toml` 的依赖保持同步，改动任一处须同步其余。

## 2. Docker 开发栈

完整栈启动前，在 **Docker daemon 所在的 Linux 宿主机**准备沙箱共享目录
（仅启动 redis 时无需此步骤）：

```bash
# 镜像内 harness 用户固定为 UID/GID 1000；目录仅供该用户写入
sudo install -d -m 0700 -o 1000 -g 1000 /tmp/llm-harness-sandbox
docker pull python:3.11-slim           # 默认沙箱镜像，worker 镜像不包含它
```

开发与生产编排都将该目录按相同绝对路径挂入 worker，并将 `TMPDIR` 指向它。
worker 经宿主 docker.sock 启动的是兄弟容器：Docker 的 bind source 在宿主解析，
不能使用只存在于 worker 内的 `/tmp/llm-harness-sandbox-*` 路径。
每个用例仍使用独立随机子目录；沙箱仅只读挂载该子目录，执行结束后自动清理。

可在 `.env` 设置 `SANDBOX_WORKDIR=/srv/llm-harness/sandbox`，并对该路径执行同样的
`install -d` 命令。必须使用宿主可见、UID 1000 可写的绝对路径；Compose 同步将其用于
source、target 与 TMPDIR。只设置 worker 的 TMPDIR 或只改一侧挂载路径都不够。
目录缺失时 Compose 拒绝自动创建，以免产生 root 属主的不可写目录；默认 `/tmp`
可能随重启清空，重启后须重新准备，长期部署建议使用上述 `/srv` 路径。

```bash
docker compose up -d                 # postgres + redis + api + worker + beat
docker compose logs -f api           # 跟踪 API 日志
docker compose down                  # 停止（卷保留）
docker compose down -v               # 停止并清空数据卷
```

- API 地址 `http://localhost:8000`，健康检查 `GET /api/v1/health`。
- 只想跑集成测试时用法不变：`docker compose up -d redis` +
  `bash scripts/run_integration_tests.sh`（redis 服务定义未改动）。
- 镜像内以非 root 用户 `harness` 运行；数据落在命名卷
  （`postgres_data` / `uploads_data` / `task_data`）。

## 3. 生产部署

前置条件：项目根目录有从 `.env.example` 复制的 `.env`，其中
`SECRET_KEY`（≥32 字节）与 `ENCRYPTION_KEY`（Fernet）**必须已填写**——生产编排的
`env_file` 是必选项，且 `DATABASE_PASSWORD` 未设置时 compose 会直接报错拒绝启动。
若启用沙箱（worker 挂载宿主 docker.sock），还需设置 `DOCKER_GID` 为宿主 docker
组的 GID（查询：`stat -c %g /var/run/docker.sock`），未设置同样拒绝启动。
还需按第 2 节准备共享目录及沙箱镜像；可在 `.env` 设置 `SANDBOX_WORKDIR`
指向持久目录。已有部署升级后须重建 worker，使 TMPDIR 与挂载配置生效。

```bash
cp .env.example .env
# 生成密钥：
python3 -c "import secrets; print(secrets.token_urlsafe(48))"                              # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" # ENCRYPTION_KEY

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

启动后在 worker 内验证目录与真实沙箱执行链路（开发部署去掉 `-f` 参数）：

```bash
docker compose -f docker-compose.prod.yml exec -T worker python - <<'PY'
import os
import tempfile
from pathlib import Path
from src.models import SandboxConfig
from src.sandbox_executor import SandboxExecutor

root = Path(os.environ["TMPDIR"])
assert root.is_absolute() and os.access(root, os.W_OK | os.X_OK), root
assert Path(tempfile.gettempdir()) == root, "tempfile 回退到非共享目录，请检查权限"
ok, detail = SandboxExecutor(SandboxConfig()).health_check()
assert ok, detail
print("sandbox preflight passed")
PY
```

生产栈拓扑：`nginx:80 → api:8000`（内部端口不对外），postgres/redis 仅内网，
worker 挂载宿主 `/var/run/docker.sock` 执行沙箱（**确认安全边界后再启用**，
并设置 `DOCKER_GID`），全部服务 `restart: unless-stopped`，日志经 json-file
驱动轮转（10 MiB × 3）。api 服务设置了 `FORWARDED_ALLOW_IPS`，uvicorn 信任
nginx 传来的 `X-Forwarded-For`，应用层限流与审计按真实客户端 IP 计数；
若自行改变拓扑（如再叠加一层代理），需同步调整该值。

HTTPS：按 `deploy/nginx/nginx.conf` 末尾的注释模板签发 Let's Encrypt 证书、
挂载 `deploy/nginx/certs/`、放开 443 端口并添加 80→443 跳转。

限流对齐关系（nginx 与应用双层）：`/api/v1/auth/*` 10 req/min（`AUTH_RATE_LIMIT`），
其余 API 120 req/min（`AUTH_PROTECTED_RATE_LIMIT`）；请求体上限 100 MiB
（`FILE_UPLOAD_MAX_BYTES`）。调整任一侧时同步另一侧。

### 日志

`LOG_FORMAT=json`（生产默认）时应用与 uvicorn 日志均为 JSON 行；`LOG_LEVEL`
控制级别。轮转由 compose 的 logging 驱动负责（见 prod 编排），
集中采集接 docker logging driver 或 stdout 收集器。Sentry / Prometheus 为
issue 标注的可选项，当前未接线，接入时从 `docker-compose.prod.yml` 的
environment 出发，不修改应用代码。

## 4. 数据库迁移与回滚

迁移由 Alembic 管理，**API 启动时自动执行**（lifespan 内
`EvaluationResultsService` 构造时调用 `api/db/migrate.py` 的 `run_migrations`），
无需手动步骤；迁移版本在 `api/db/migrations/versions/`。编排层面，worker 依赖
`api: service_healthy`——api 健康即迁移完成，因此 worker 不会在缺表窗口消费任务；
若绕开编排手动部署，先启动 API 并确认 `GET /api/v1/health` 返回 200 后再扩 worker。

手动操作（危险操作前先备份）：

```bash
python3 -c "
from api.db.engine import business_database_url, make_engine
from api.db.migrate import upgrade, downgrade, offline_upgrade_sql
print(offline_upgrade_sql(business_database_url()))   # 预览将执行的 SQL（不连库）
engine = make_engine(business_database_url())
upgrade(engine)        # 升级到最新
# downgrade(engine, '0001')   # 回滚到指定版本（会丢弃其后版本的 schema 变更）
"
```

- 回滚策略：优先用数据库快照/卷备份恢复（`docker volume` 备份 postgres_data），
  Alembic downgrade 仅用于开发环境。
- 种子数据（幂等，可重复执行）：

```bash
python3 scripts/seed_data.py                                # 使用 .env 的 DATABASE_URL
python3 scripts/seed_data.py --database-url sqlite:///./data/business/seed-demo.sqlite3
```

示例题按 function 协议执行，使用 `solution(nums, target)` 或 `solution(s)`；
`test_cases` 中的 `input` 是参数字典，`expected_output` 保留数组、布尔和整数类型。
已导入旧版示例的部署更新代码后，对同一业务数据库重新运行上述 seed 命令即可原位修复，
无需删库或清空题库。示例用例属于公开样例，不提供独立隐藏评分。

## 5. 环境变量速查

完整样例见 `.env.example`（与 Settings 字段一致性有测试保证）。关键项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `HOST` / `PORT` | `localhost` / `8000` | API 监听地址（.env 按字段名匹配，compose 里可写 `API_HOST`） |
| `DATABASE_URL` | 空 → SQLite | 业务库；生产用 `postgresql+psycopg://...` |
| `SECRET_KEY` | 必填 | JWT 签名密钥，≥32 字节，缺失时启动失败 |
| `ENCRYPTION_KEY` | 必填 | Fernet 密钥，用于 API Key 加密存储 |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | 队列与结果后端 |
| `UPLOAD_DIR` / `FILE_UPLOAD_MAX_BYTES` | `uploads` / 100 MiB | 上传目录与上限（nginx `client_max_body_size` 需对齐） |
| `DATA_ROOT` / `TASK_SERVICE_ROOT` | `data` / `./data/tasks` | 数据集与任务存储 |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | 日志级别与格式（`json` 为生产推荐） |

## 6. 故障排查

| 现象 | 排查 |
| --- | --- |
| 启动报 `SECRET_KEY ... at least 32 bytes` / `ENCRYPTION_KEY must be a Fernet key` | `.env` 未填或格式错误的密钥；用第 3 节命令重新生成 |
| 生产 `compose up` 报 `DATABASE_PASSWORD must be set` | `.env` 缺 `DATABASE_PASSWORD`（生产编排强制要求） |
| API 容器反复重启 | `docker compose -f docker-compose.prod.yml logs api`；常见为 postgres 未就绪或迁移失败 |
| worker 不消费任务 | 确认 `CELERY_BROKER_URL` 与 api 一致；`docker compose logs worker` 看队列名（`evaluations`、`default`） |
| worker 内 `docker` 命令 permission denied（Linux） | `DOCKER_GID` 与宿主 docker 组不一致：`stat -c %g /var/run/docker.sock` 后更新 `.env` 并重建 |
| worker 启动报 bind source 不存在，或预检报 `bind source path does not exist` / runner 缺失 | 按第 2 节在 Docker 宿主创建 SANDBOX_WORKDIR 并赋予 UID/GID 1000 权限；确认 TMPDIR 与宿主挂载路径相同，再执行第 3 节真实预检 |
| worker 内 `docker` 命令 permission denied（macOS Docker Desktop） | Desktop 的 socket 在 VM 内属 `root:root 660`，`group_add` 无法匹配；沙箱宿主 docker 调用仅支持 Linux 宿主机，Desktop 上验证部署时忽略该项 |
| WebSocket 连不上 | 确认经 nginx 访问（`/api/v1/ws` 前缀带升级头）；直连时检查代理是否剥离 `Upgrade` 头 |
| 上传 413 | nginx `client_max_body_size` 小于 `FILE_UPLOAD_MAX_BYTES`；两侧对齐 |
| 集成测试全部 skip | redis 未启动：`docker compose up -d redis` |
| 迁移失败 | 先 `offline_upgrade_sql` 预览 SQL；检查 `DATABASE_URL` 指向的库版本与迁移链 |
