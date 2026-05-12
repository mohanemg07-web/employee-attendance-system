# Tasks package — expose celery_app for Docker command
from app.tasks.sync import celery_app

# Register additional sync tasks so Celery autodiscovers them
import app.tasks.sync_monthly  # noqa: F401
import app.tasks.sync_users    # noqa: F401

__all__ = ["celery_app"]
