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
# 导入任务模块完成 Celery 注册；任务本身仍通过数据库租约保证可恢复。
from app.jobs import tasks as _tasks  # noqa: E402,F401
