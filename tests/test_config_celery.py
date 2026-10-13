"""测试 Celery 配置设置。"""


def test_settings_has_celery_broker_url():
    """测试 Settings 类包含 CELERY_BROKER_URL 配置。"""
    from api.config import Settings

    settings = Settings()
    assert hasattr(settings, "CELERY_BROKER_URL")
    assert settings.CELERY_BROKER_URL is not None
    assert "redis://" in settings.CELERY_BROKER_URL


def test_settings_has_celery_result_backend():
    """测试 Settings 类包含 CELERY_RESULT_BACKEND 配置。"""
    from api.config import Settings

    settings = Settings()
    assert hasattr(settings, "CELERY_RESULT_BACKEND")
    assert settings.CELERY_RESULT_BACKEND is not None
    assert "redis://" in settings.CELERY_RESULT_BACKEND


def test_settings_has_task_service_root():
    """测试 Settings 类包含 TASK_SERVICE_ROOT 配置。"""
    from api.config import Settings

    settings = Settings()
    assert hasattr(settings, "TASK_SERVICE_ROOT")
    assert settings.TASK_SERVICE_ROOT is not None
    assert isinstance(settings.TASK_SERVICE_ROOT, str)
