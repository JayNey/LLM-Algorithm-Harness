# 异步任务队列部署指南

## 概述

本指南详细说明如何在生产环境中部署和配置异步任务队列系统。异步任务队列采用 Celery + Redis 架构，用于处理长时间运行的评估任务。

## 前置要求

1. **Redis** ≥ 6.0
   - 用于消息代理和结果后端
   - 推荐使用官方 Redis 或 AWS ElastiCache/Azure Cache for Redis

2. **Python** ≥ 3.10
   - 支持项目所有依赖库

3. **数据库**
   - 开发环境：SQLite
   - 生产环境：PostgreSQL ≥ 12（推荐）或 MySQL ≥ 5.7

4. **系统资源**
   - CPU：4+ 核（生产环境）
   - 内存：8GB+（4GB 最小）
   - 磁盘：20GB+（用于日志、数据和临时文件）

## 真实评估运行前置

本 change 起，异步评估 worker 不再返回模拟结果，而是经真实 `AlgorithmHarness` 执行（LLM 调用 + Docker 沙箱运行 + 成本统计）。因此运行评估 worker 的机器必须额外满足以下硬前置，否则任务会在执行前或首单元即失败。

1. **Docker 守护进程**
   - `SandboxConfig()` 默认 `backend="docker"`（`docker_image` 默认 `python:3.11-slim`）。
   - `AlgorithmHarness._prepare_strategy_runtime()` 在构造每个策略运行时会调用 `SandboxExecutor.health_check()`，Docker 不可用（daemon 未运行或镜像缺失）时抛 `RuntimeError("Sandbox preflight failed: ...")`，评估在 preflight 阶段即 fail-fast，任务被置为 `failed`。
   - 部署机必须提供可用的 Docker daemon，并**预先拉取**目标镜像（如 `docker pull python:3.11-slim`），避免首个执行单元因拉取镜像而超时。
   - 仅测试用途可显式配置 `backend="host"`；生产评估不应依赖 host 后端。

2. **worker 工作目录约定**
   - 评估执行体使用 `TaskService(root=f"data/tasks/{evaluation_id}")` 创建逐单元运行目录，该路径为**相对路径**。
   - Celery worker 必须在仓库根目录启动，或确保 `data/tasks/` 相对于进程 CWD 可写，否则任务运行目录创建失败。下方 systemd 示例的 `WorkingDirectory=/opt/llm-harness` 与 supervisor 示例的 `directory=/opt/llm-harness` 必须指向包含 `data/tasks/` 的仓库根；如服务由其他路径拉起，请相应设置 `--workdir`/`WorkingDirectory=`/`directory=`。

3. **凭证与 `model`**
   - 创建评估请求必须携带必填 `model`，且 `api_key_id` 必须可解析为该用户的有效凭证；否则任务在执行前即置 `failed`（fail-fast，见 §5.4/§5.5）。缺失 `model` 的请求在 HTTP 层即返回 422。

## 环境变量配置

### 核心配置

```bash
# Redis 配置
CELERY_BROKER_URL=redis://redis-host:6379/0
CELERY_RESULT_BACKEND=redis://redis-host:6379/1

# 数据库配置
DATABASE_URL=postgresql://user:password@db-host:5432/llm_harness

# API 服务配置
API_HOST=0.0.0.0
API_PORT=8000

# 任务服务配置
TASK_SERVICE_ROOT=/var/data/llm-harness/tasks
```

### Redis 连接选项

对于需要认证的 Redis：

```bash
CELERY_BROKER_URL=redis://:password@redis-host:6379/0
CELERY_RESULT_BACKEND=redis://:password@redis-host:6379/1
```

对于使用 Redis Cluster：

```bash
CELERY_BROKER_URL=redis-cluster://redis-node-1:6379,redis-node-2:6379,redis-node-3:6379/0
```

### 可选配置

```bash
# 日志级别
LOG_LEVEL=info

# Worker 并发数
CELERY_CONCURRENCY=4

# 任务超时（秒）
CELERY_TASK_TIME_LIMIT=3600

# 结果过期时间（秒）
CELERY_RESULT_EXPIRES=86400
```

## 生产环境部署

### 1. Redis 配置

#### 独立 Redis 实例

```bash
# Docker Compose
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

#### 推荐的 Redis 生产配置

编辑 `/etc/redis/redis.conf`：

```conf
# 持久化
save 900 1
save 300 10
save 60 10000
appendonly yes
appendfsync everysec

# 内存策略
maxmemory 2gb
maxmemory-policy allkeys-lru

# 网络
bind 127.0.0.1 ::1
protected-mode yes
port 6379

# 性能
tcp-backlog 511
timeout 0
tcp-keepalive 300

# 日志
loglevel notice
logfile "/var/log/redis/redis-server.log"
```

启动 Redis：

```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 2. 数据库迁移

初始化数据库架构：

```bash
# 安装迁移工具
pip install alembic sqlalchemy

# 运行迁移
alembic upgrade head
```

### 3. Celery Worker 配置

#### 使用 Systemd 服务

创建 `/etc/systemd/system/celery-worker.service`：

```ini
[Unit]
Description=Celery Worker for LLM Harness
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=llm-harness
Group=llm-harness
WorkingDirectory=/opt/llm-harness

# Environment variables
EnvironmentFile=/opt/llm-harness/.env
Environment="PYTHONUNBUFFERED=1"
Environment="CELERY_BROKER_URL=redis://localhost:6379/0"

# Pre-start
ExecStartPre=/opt/llm-harness/venv/bin/python -m alembic upgrade head

# Start
ExecStart=/opt/llm-harness/venv/bin/celery \
    -A src.celery_app \
    worker \
    --loglevel=info \
    --concurrency=4 \
    --pidfile=/var/run/celery/worker.pid \
    --logfile=/var/log/celery/worker.log \
    --max-tasks-per-child=1000

# Restart policy
Restart=on-failure
RestartSec=10

# Limits
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

创建所需的目录和权限：

```bash
# 创建用户和组
sudo useradd -r -s /bin/bash llm-harness

# 创建目录
sudo mkdir -p /opt/llm-harness
sudo mkdir -p /var/run/celery
sudo mkdir -p /var/log/celery
sudo mkdir -p /var/data/llm-harness/tasks

# 设置权限
sudo chown -R llm-harness:llm-harness /opt/llm-harness
sudo chown -R llm-harness:llm-harness /var/run/celery
sudo chown -R llm-harness:llm-harness /var/log/celery
sudo chown -R llm-harness:llm-harness /var/data/llm-harness
```

启动 Worker：

```bash
sudo systemctl daemon-reload
sudo systemctl start celery-worker
sudo systemctl enable celery-worker
sudo systemctl status celery-worker
```

#### 使用 Supervisor

创建 `/etc/supervisor/conf.d/celery-worker.conf`：

```ini
[program:celery-worker]
command=/opt/llm-harness/venv/bin/celery -A src.celery_app worker --loglevel=info --concurrency=4
directory=/opt/llm-harness
user=llm-harness
numprocs=1
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
```

启动：

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start celery-worker
```

### 4. API 服务配置

使用 Gunicorn + Nginx 部署 API：

#### Gunicorn 配置

创建 `/etc/systemd/system/llm-harness-api.service`：

```ini
[Unit]
Description=LLM Harness API
After=network.target postgresql.service

[Service]
Type=notify
User=llm-harness
Group=llm-harness
WorkingDirectory=/opt/llm-harness

EnvironmentFile=/opt/llm-harness/.env
Environment="PYTHONUNBUFFERED=1"

ExecStart=/opt/llm-harness/venv/bin/gunicorn \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind unix:/var/run/llm-harness/api.sock \
    --timeout 120 \
    --access-logfile /var/log/llm-harness/api.log \
    --error-logfile /var/log/llm-harness/api-error.log \
    api.main:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Nginx 配置

创建 `/etc/nginx/sites-available/llm-harness`：

```nginx
upstream llm_harness {
    server unix:/var/run/llm-harness/api.sock fail_timeout=0;
}

server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 代理设置
    location / {
        proxy_pass http://llm_harness;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;

        # 增加超时以支持长时间运行的请求
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # 日志
    access_log /var/log/nginx/llm-harness.access.log;
    error_log /var/log/nginx/llm-harness.error.log;
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/llm-harness /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5. 监控和告警

#### Prometheus 指标采集

Celery 集成 Prometheus 客户端，暴露以下指标：

```
celery_task_sent_total{task_type="evaluation"}
celery_task_received_total{task_type="evaluation"}
celery_task_started_total{task_type="evaluation"}
celery_task_succeeded_total{task_type="evaluation"}
celery_task_failed_total{task_type="evaluation"}
celery_task_rejected_total{task_type="evaluation"}
celery_queue_length{queue="default"}
celery_worker_state{state="online"}
redis_memory_used_bytes
```

#### 告警规则

创建 `/etc/prometheus/rules/celery.yml`：

```yaml
groups:
  - name: celery_alerts
    rules:
      - alert: HighTaskFailureRate
        expr: rate(celery_task_failed_total[5m]) > 0.05
        for: 5m
        annotations:
          summary: "高任务失败率"
          description: "过去5分钟内任务失败率 > 5%"

      - alert: QueueBacklog
        expr: celery_queue_length > 100
        for: 10m
        annotations:
          summary: "任务队列积压"
          description: "队列中有 {{ $value }} 个待处理任务"

      - alert: WorkerDown
        expr: count(celery_worker_state{state="online"}) < 2
        for: 5m
        annotations:
          summary: "Worker 下线"
          description: "在线 Worker 数少于 2 个"

      - alert: HighRedisMemory
        expr: redis_memory_used_bytes / 1024 / 1024 / 1024 > 1.6
        for: 5m
        annotations:
          summary: "Redis 内存使用过高"
          description: "Redis 内存使用率超过 80%（已用 {{ $value }}GB）"
```

#### 日志聚合

使用 ELK Stack（Elasticsearch + Logstash + Kibana）或 Loki：

**Logstash 配置示例**：

```conf
input {
  file {
    path => "/var/log/celery/worker.log"
    start_position => "beginning"
    tags => ["celery-worker"]
  }
}

filter {
  grok {
    match => { "message" => "\[%{TIMESTAMP_ISO8601:timestamp}\] %{LOGLEVEL:log_level} %{DATA:logger} %{GREEDYDATA:message}" }
  }
  mutate {
    add_field => { "service" => "celery-worker" }
    add_field => { "environment" => "production" }
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "celery-logs-%{+YYYY.MM.dd}"
  }
}
```

## 监控工具

### Flower - Celery 监控

启动 Flower 监控界面：

```bash
celery -A src.celery_app flower \
    --port=5555 \
    --persistent=True \
    --db=/var/lib/flower/flower.db
```

配置为系统服务（`/etc/systemd/system/flower.service`）：

```ini
[Unit]
Description=Flower - Celery Monitoring
After=network.target redis.service

[Service]
Type=simple
User=llm-harness
Group=llm-harness
WorkingDirectory=/opt/llm-harness

EnvironmentFile=/opt/llm-harness/.env
ExecStart=/opt/llm-harness/venv/bin/celery -A src.celery_app flower \
    --port=5555 \
    --persistent=True \
    --db=/var/lib/flower/flower.db \
    --logfile=/var/log/flower/flower.log

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

访问 Web 界面：http://your-server:5555

## 故障排查

### Worker 无法启动

**症状**：Worker 进程立即退出，日志中显示连接错误

**排查步骤**：

```bash
# 检查 Redis 连接
redis-cli ping
# 预期输出：PONG

# 检查 Celery 配置
celery -A src.celery_app inspect active

# 查看详细日志
tail -f /var/log/celery/worker.log

# 测试 Broker 连接
celery -A src.celery_app shell
>>> from src.celery_app import app
>>> app.connection()
```

**常见原因**：

- Redis 未运行：启动 Redis 服务
- Redis 连接信息错误：检查 `CELERY_BROKER_URL`
- Worker 权限不足：检查文件系统权限
- 数据库迁移未完成：运行 `alembic upgrade head`

### 任务卡在 Pending 状态

**症状**：任务已创建但长时间不执行，状态保持为 "pending"

**排查步骤**：

```bash
# 检查 Worker 是否在线
celery -A src.celery_app inspect active_queues

# 检查队列配置
celery -A src.celery_app inspect registered

# 检查 Broker 消息数
redis-cli LLEN celery
```

**解决方案**：

1. 确保至少有一个 Worker 在线
2. 检查 Worker 日志中是否有错误
3. 重启 Worker：`sudo systemctl restart celery-worker`
4. 清理卡住的任务：`celery -A src.celery_app purge`（警告：将删除所有任务）

### 任务失败重试过多

**症状**：任务不断失败和重试，日志中显示相同的错误

**分析和解决**：

```python
# 区分错误类型
# 1. 业务错误（应该立即失败）
# 2. 临时错误（应该重试）
# 3. 基础设施错误（需要人工介入）

# 在 Celery 任务中配置重试策略
from celery import Task

class CallbackTask(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
```

### Redis 内存溢出

**症状**：Redis 无响应或连接超时

**排查**：

```bash
redis-cli info memory
# 查看 used_memory、max_memory 等指标

# 检查最大内存策略
redis-cli CONFIG GET maxmemory-policy
```

**解决方案**：

1. 增加 Redis 内存分配：更新 `maxmemory` 配置
2. 清理过期的任务结果：`redis-cli EXPIRE celery:* 86400`
3. 监控 Redis 内存增长，检查是否有内存泄漏

### 高 CPU 使用率

**症状**：Worker 进程 CPU 使用率持续高于 80%

**排查**：

```bash
# 查看 Worker 的活跃任务
celery -A src.celery_app inspect active

# 查看正在运行的工作
celery -A src.celery_app inspect stats
```

**解决方案**：

1. 增加 Worker 并发数：`--concurrency=8`
2. 使用进程池替代线程池
3. 优化任务代码，减少 CPU 消耗
4. 分离长时间运行的任务到单独的 Worker

## 性能优化建议

1. **Worker 池大小**：根据 CPU 核心数设置，建议 `核心数 * 2` 到 `核心数 * 4`

2. **任务优先级**：使用队列隔离高优先级和低优先级任务

3. **结果后端**：对于高吞吐量场景，考虑使用专用的结果存储

4. **监控和告警**：定期检查 Worker 状态和任务失败率

5. **定期维护**：定期清理过期的任务结果和日志

## 扩展和升级

### 水平扩展

增加更多的 Worker 实例：

```bash
# 启动第二个 Worker（指定不同的名称）
celery -A src.celery_app worker --hostname=worker2@%h

# 使用 Docker Swarm 或 Kubernetes 可以自动管理多个 Worker
```

### 版本升级

升级 Celery 或 Redis：

```bash
# 升级依赖
pip install --upgrade celery redis

# 确保向后兼容性
celery -A src.celery_app inspect ping

# 分阶段重启 Worker（避免任务丢失）
supervisorctl restart celery-worker
```

## 相关文档

- [Celery 官方文档](https://docs.celeryproject.io/)
- [Redis 官方文档](https://redis.io/documentation)
- [Flower 文档](https://flower.readthedocs.io/)
- [项目 README](../../README.md)
