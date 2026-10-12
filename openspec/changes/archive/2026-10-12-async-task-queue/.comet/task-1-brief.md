# Task 1: Celery 基础设施搭建

## 任务目标

搭建 Celery + Redis 异步任务队列的基础设施，包括 Celery 应用配置、依赖管理、环境变量配置和 worker 启动脚本。

## 文件操作

**创建**：
- `src/celery_app.py` - Celery 应用实例和配置
- `.env.example` - 环境变量模板（如不存在）
- `scripts/start_worker.sh` - Worker 启动脚本

**修改**：
- `requirements.txt` 或 `pyproject.toml` - 添加 Celery 和 Redis 依赖
- `api/config.py` - 添加 Celery 配置项到 Settings 类

## 接口契约

**Produces**：
- `celery_app: Celery` - 配置好的 Celery 应用实例
- 环境变量：`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `TASK_SERVICE_ROOT`

**Consumes**: 无

## 实现步骤

### 步骤 1: 添加依赖

修改 `requirements.txt` 或 `pyproject.toml`，添加：

```txt
celery[redis]>=5.3.0
redis>=5.0.0
```

### 步骤 2: 安装依赖

```bash
pip install celery[redis]>=5.3.0 redis>=5.0.0
```

预期：安装成功，无错误

### 步骤 3: 创建 Celery 应用配置

创建 `src/celery_app.py`：

```python
"""Celery application for async task processing."""

from celery import Celery
from kombu import Exchange, Queue

# 延迟导入避免循环依赖
celery_app = Celery("llm_harness")

def configure_celery():
    """配置 Celery，在导入 settings 后调用。"""
    from api.config import settings
    
    celery_app.conf.update(
        broker_url=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,
        result_expires=7 * 24 * 3600,  # 7 天
        
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        
        timezone="UTC",
        enable_utc=True,
        
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=50,
        
        task_routes={
            "src.tasks.evaluation.*": {"queue": "evaluations"},
        },
        
        task_default_queue="default",
        task_default_exchange="default",
        task_default_routing_key="default",
        
        task_queues=(
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("evaluations", Exchange("evaluations"), routing_key="evaluations"),
        ),
        
        task_track_started=True,
        task_send_sent_event=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
    )

# 自动发现任务
celery_app.autodiscover_tasks(["src.tasks"])

# 初始化配置
configure_celery()
```

### 步骤 4: 添加配置到 api/config.py

在 `api/config.py` 的 `Settings` 类中添加：

```python
# Celery 配置
CELERY_BROKER_URL: str = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

# TaskService 存储路径
TASK_SERVICE_ROOT: str = "./data/tasks"
```

### 步骤 5: 更新 .env.example

在 `.env.example` 中添加（如文件不存在则创建）：

```bash
# Celery 配置
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# TaskService
TASK_SERVICE_ROOT=./data/tasks
```

### 步骤 6: 创建 worker 启动脚本

创建 `scripts/start_worker.sh`：

```bash
#!/bin/bash
# Celery worker 启动脚本

export PYTHONPATH="${PYTHONPATH}:$(pwd)"

celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --max-tasks-per-child=50 \
    --queues=evaluations,default \
    --hostname=worker@%h
```

### 步骤 7: 赋予启动脚本执行权限

```bash
chmod +x scripts/start_worker.sh
```

### 步骤 8: 验证配置

```bash
python -c "from src.celery_app import celery_app; print(celery_app.conf.broker_url)"
```

预期：输出 `redis://localhost:6379/0`（或配置的 URL）

### 步骤 9: 提交

```bash
git add requirements.txt src/celery_app.py api/config.py .env.example scripts/start_worker.sh
git commit -m "feat: add Celery基础设施配置"
```

## 全局约束

- Python ≥ 3.10
- Celery ≥ 5.3.0
- Redis ≥ 6.0
- 所有异步任务必须支持 pause/resume
- 错误必须区分业务错误（不重试）和基础设施错误（自动重试）
- 数据库操作必须在事务内完成
- 所有 API 响应必须包含标准的 ApiResponse 格式

## 验收标准

- [ ] Celery 依赖已添加到 requirements.txt 或 pyproject.toml
- [ ] Celery 依赖已成功安装
- [ ] `src/celery_app.py` 文件已创建，包含完整配置
- [ ] `api/config.py` 已添加 Celery 相关配置字段
- [ ] `.env.example` 文件已创建或更新，包含 Celery 环境变量
- [ ] `scripts/start_worker.sh` 已创建且具有执行权限
- [ ] 验证命令成功执行，输出正确的 broker URL
- [ ] 所有变更已提交到 Git
