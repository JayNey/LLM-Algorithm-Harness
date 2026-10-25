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

- API 地址 `http://localhost:8000`，存活检查 `GET /api/v1/health`；就绪检查 `GET /api/v1/health/ready`：仅 HTTP 200 表示基础 API 就绪，503 或超时表示不可准入。管理员诊断使用 `/api/v1/system/health`，需管理员身份，详见[健康接口契约](../api-monitoring.md#健康接口契约)。
- 就绪检查无需认证，200 返回 `{"status":"ready"}`，503 返回 `{"status":"not_ready"}`；响应 `no-store`，1 秒响应预算和 1 秒进程内缓存。
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
`api: service_healthy`，镜像探测仍是 `/api/v1/health`，仅等待进程可响应。
生产 nginx 在业务请求、认证请求与 WebSocket 握手前，以 GET 子请求访问
`/api/v1/health/ready`；探测失败或超时则返回 503、不转发业务请求。
就绪子请求不携带客户端请求体、查询参数或凭据，连接/读/写超时均为 2 秒，
不开启代理缓存；API 自身仍使用 1 秒探测缓存，故恢复和失败判定存在该缓存窗口。
健康接口和 `/api/v1/system/` 管理员诊断不经过准入或业务限流；管理员鉴权仍由 API 执行。
开发栈直连 API 不包含 nginx，因此不具备该边缘准入。

迁移失败或数据库不可用时，存活接口仍可能为 200，应以就绪接口决定是否放行业务流量。
就绪恢复 200 后，后续请求自动重新准入；已建立的 WebSocket 不会因此主动断开。
单实例 nginx 的子请求和业务请求指向同一 API；多副本部署应让负载均衡器按每个实例的
就绪接口摘除未就绪实例，不能将随机副本的成功探测当成其他副本的准入依据。
基础 API 就绪不保证 Redis 提交、worker、沙箱或模型提供商可用，启动/扩容 worker
还需独立确认 broker 与实际执行环境。`/api/v1/system/health` 仅供管理员诊断。

### 探针与故障验收

- 镜像 `HEALTHCHECK` / 平台 liveness：`/api/v1/health`，保留原有配置。
- 平台 readiness / 负载均衡器健康检查：`/api/v1/health/ready`，仅 200 成功；超时 3 秒、间隔 5 秒、连续 2 次失败摘除、连续 2 次成功恢复可作为初始配置。
- 业务可用性告警：同一就绪 URL，503、其他状态、连接错误、超时均失败，不跟随重定向；参见[监控示例](../api-monitoring.md#部署可用性告警)。

```bash
# 在实际业务入口验证；地址替换为部署域名（HTTPS 模板须复制完整准入与豁免配置）。
curl --max-time 3 -i http://localhost/api/v1/health
curl --max-time 3 -i http://localhost/api/v1/health/ready
```

在隔离测试环境模拟数据库不可用或迁移版本不匹配，等待缓存过期：存活应仍为 200，
就绪应为 503，业务入口及新 WebSocket 握手应为 503，管理员仍能访问诊断（需鉴权）。
恢复数据库后，就绪变为 200，业务请求恢复正常鉴权/响应。另检查监控目标不可达与超时
也会告警，不能仅模拟返回码。不对生产数据库直接执行破坏性故障注入。

仓库回归 `python3 -m pytest tests/test_deployment_readiness.py -q --no-cov`
使用本机 nginx 和受控 HTTP 上游验证准入、恢复、超时、原业务错误保留及探针限流豁免；
需安装带 `http_auth_request_module` 的 nginx（`nginx -V` 可检查，官方 nginx 镜像包含此模块）。
测试不启动系统 nginx 服务；缺少可执行文件时跳过，不能将跳过视为联调通过。

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

## 7. 监控部署与验收（#157）

先配置 `MONITOR_ADMIN_USER_IDS` 并使用有效管理员 Bearer token。详细字段与边界见[监控指南](../api-monitoring.md)。

- `MONITOR_QUEUE_PROBES_ENABLED=true` 启用 Redis PING、配置队列各优先级分桶 LLEN 与 worker 只读快照；升级后重启 worker。broker waiting、数据库 pending 和 worker reserved 是独立非原子观测，不能相加；禁用或失败时 null 不代表零负载。
- `MONITOR_CONTAINER_PROBES_ENABLED=true` 启用当前 API Docker context 中带 `io.llm-algorithm-harness.sandbox=v1` 标签的运行容器资源采样。默认关闭，旧无标签容器不在范围；API 的 Docker context 不证明远程 worker 执行环境可用。
- API 与 worker/CLI 需配置同一 `AUTH_DATABASE_PATH`、可共同访问的认证 SQLite 文件和一致的 `SECRET_KEY`/`ENCRYPTION_KEY`，才能共享事件、LLM 尝试、缓存快照及用户计量。`DATABASE_URL` 是独立业务数据库，单独共享它不足以共享监控。当前 Compose 不提供跨服务共享认证 SQLite 的专用命名卷，不能据默认栈宣称已完成跨容器采集；部署方须配置并验证共享存储。多主机 SQLite 共享的部署适用性需另行评估。
- `USER_DAILY_API_CALL_LIMIT` / `USER_MONTHLY_API_CALL_LIMIT` 作用于用户生成 SDK 尝试，空值无限、0 禁止、负值无效；API 与所有 worker 加载相同设置。UTC 日/月周期在北京时间 08:00 切换。额度与 HTTP 请求限流独立；失败和重试也消耗次数。
- `/system/config` 仅反映当前 API 进程白名单配置；`/config/providers` 默认静态目录，传入本人 `api_key_id` 才查动态目录，均要求管理员。模型枚举成功不保证生成成功。

本次文档同步的[验收记录](../superpowers/reports/2026-10-25-sync-monitoring-docs-acceptance-verify.md)列出代码基线、检查命令及实际结果。部署验收时须在目标环境另行确认 PostgreSQL、Redis/Celery、目标队列消费者、worker 沙箱及真实供应商调用；离线测试或 `/health/ready` 的 200 不替代这些证据。

在隔离环境复验已有可选集成检查：

```bash
# 指向隔离 Redis，预先启动本版本 worker；仅检查观测，不提交业务任务
MONITOR_QUEUE_TEST_BROKER=redis://localhost:6379/0 python3 -m pytest tests/test_monitoring_queue_integration.py --no-cov -q
# 需 Docker daemon 与已拉取的沙箱镜像；测试会创建并清理自身容器
MONITOR_CONTAINER_TESTS=1 python3 -m pytest tests/test_monitoring_container_integration.py --no-cov -q
```

这两项仅验证相应观测，仍不构成真实模型评估全链路验收。
