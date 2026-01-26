try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None

from api.core.config import settings

if CELERY_AVAILABLE and Celery:
    celery = Celery(
        "retv4",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
    )

    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_time_limit=60 * 60,
    )
else:
    # Fallback mock Celery for development
    class MockCelery:
        def task(self, *args, **kwargs):
            def decorator(func):
                def wrapper(*a, **kw):
                    return func(*a, **kw)
                return wrapper
            return decorator
    
    celery = MockCelery()

