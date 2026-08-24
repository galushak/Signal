from celery import Celery

from .settings import get_settings

settings = get_settings()
celery_app = Celery("signage", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "signage"


@celery_app.task(name="signage.media.prepare")
def prepare_media(asset_id: str) -> dict[str, str]:
    """Placeholder for FFmpeg/PDF/image processing, executed outside the API."""
    return {"asset_id": asset_id, "status": "queued"}
