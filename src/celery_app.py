"""Celery application for async task processing."""

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

# 延迟导入避免循环依赖
celery_app = Celery("llm_harness")


def configure_celery() -> None:
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
            "src.tasks.cleanup.*": {"queue": "default"},
            "src.tasks.experiment.*": {"queue": "default"},
            "src.tasks.imports.*": {"queue": "default"},
            "src.tasks.benchmark.*": {"queue": "default"},
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
        # Celery Beat 定时任务配置
        include=[
            "src.tasks.evaluation",
            "src.tasks.cleanup",
            "src.tasks.experiment",
            "src.tasks.imports",
        ],
        beat_schedule={
            "cleanup-old-tasks": {
                "task": "src.tasks.cleanup.cleanup_old_tasks",
                "schedule": crontab(hour=2, minute=0),  # 每天凌晨 2 点执行
                "args": (7,),  # 保留 7 天的任务记录
                "options": {"queue": "default"},
            },
            "cleanup-task-count": {
                "task": "src.tasks.cleanup.cleanup_task_count",
                "schedule": crontab(hour=3, minute=0),  # 每天凌晨 3 点执行
                "args": (10000,),  # 保留最多 10000 条记录
                "options": {"queue": "default"},
            },
        },
    )


# 自动发现任务。worker 通过 conf.include 导入具体任务模块。
celery_app.autodiscover_tasks(["src.tasks"])

# 初始化配置
configure_celery()
