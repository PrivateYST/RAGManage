from celery import Celery

from app.core.config import Settings

settings = Settings()
celery_app = Celery("ragmanage", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
# Business tasks and transactional outbox are implemented in P12.
