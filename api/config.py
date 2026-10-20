"""API configuration settings."""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Server configuration
    HOST: str = os.getenv("API_HOST", "localhost")
    PORT: int = int(os.getenv("API_PORT", "8000"))

    # CORS configuration
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost",
    ]

    # Task configuration
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "5"))
    TASK_TIMEOUT_SECONDS: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "3600"))

    # Business database (issue #151). None falls back to the local SQLite file
    # in api.db.engine; production deployments point it at PostgreSQL.
    DATABASE_URL: str | None = os.getenv("DATABASE_URL") or None

    # Root directory for API-referenced datasets (issue #156). dataset_path
    # values must resolve inside this directory to prevent path traversal.
    DATA_ROOT: str = os.getenv("DATA_ROOT", "data")

    # Celery 配置
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # 日志（issue #159）。LOG_FORMAT: text（人类可读）| json（生产结构化输出）
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"

    # TaskService 存储路径
    TASK_SERVICE_ROOT: str = "./data/tasks"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Auth and API settings share the same dotenv file.


settings = Settings()
