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
