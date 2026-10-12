"""测试 Celery 应用配置。"""



def test_celery_app_exists():
    """测试 Celery 应用实例可以被导入。"""
    from src.celery_app import celery_app

    assert celery_app is not None
    assert celery_app.main == "llm_harness"


def test_celery_app_broker_url_configured():
    """测试 Celery broker URL 已配置。"""
    from src.celery_app import celery_app

    broker_url = celery_app.conf.broker_url
    assert broker_url is not None
    assert "redis://" in broker_url


def test_celery_app_result_backend_configured():
    """测试 Celery result backend 已配置。"""
    from src.celery_app import celery_app

    result_backend = celery_app.conf.result_backend
    assert result_backend is not None
    assert "redis://" in result_backend


def test_celery_app_task_serializer_json():
    """测试 Celery 任务序列化器使用 JSON。"""
    from src.celery_app import celery_app

    assert celery_app.conf.task_serializer == "json"
    assert "json" in celery_app.conf.accept_content
    assert celery_app.conf.result_serializer == "json"


def test_celery_app_queues_configured():
    """测试 Celery 队列已配置。"""
    from src.celery_app import celery_app

    queues = celery_app.conf.task_queues
    assert queues is not None
    assert len(queues) >= 2

    queue_names = [q.name for q in queues]
    assert "default" in queue_names
    assert "evaluations" in queue_names


def test_celery_app_task_routes_configured():
    """测试 Celery 任务路由已配置。"""
    from src.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert routes is not None
    assert "src.tasks.evaluation.*" in routes
    assert routes["src.tasks.evaluation.*"]["queue"] == "evaluations"
