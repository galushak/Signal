import json
import subprocess
from pathlib import Path

import fitz
from celery import Celery
from PIL import Image, ImageOps

from .database import SessionLocal
from .models import MediaAsset
from .settings import get_settings

settings = get_settings()
celery_app = Celery("signage", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "signage"


def _thumbnail(source: Path, target: Path) -> tuple[int, int]:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        image.thumbnail((640, 360))
        image.save(target, "JPEG", quality=84, optimize=True)
        return width, height


@celery_app.task(name="signage.media.prepare")
def prepare_media(asset_id: str) -> dict[str, str]:
    """Normalizes media and records a durable success or failure state."""
    with SessionLocal() as db:
        asset = db.get(MediaAsset, asset_id)
        if not asset:
            return {"asset_id": asset_id, "status": "missing"}
        source = settings.media_root / asset.original_path
        try:
            if not source.is_file():
                raise ValueError("Uploaded file is no longer available.")
            if asset.media_type == "image":
                thumb_relative = f"thumbnails/{asset.id}.jpg"
                asset.width, asset.height = _thumbnail(source, settings.media_root / thumb_relative)
                asset.processed_path, asset.thumbnail_path = asset.original_path, thumb_relative
            elif asset.media_type == "pdf":
                document = fitz.open(source)
                if document.page_count < 1:
                    raise ValueError("The PDF has no pages.")
                thumb_relative = f"thumbnails/{asset.id}.jpg"
                page_relative = f"processed/{asset.id}-page-1.jpg"
                pixmap = document.load_page(0).get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                pixmap.save(str(settings.media_root / page_relative))
                asset.width, asset.height = _thumbnail(settings.media_root / page_relative, settings.media_root / thumb_relative)
                asset.processed_path, asset.thumbnail_path = page_relative, thumb_relative
            elif asset.media_type == "video":
                processed_relative = f"processed/{asset.id}.mp4"
                thumb_relative = f"thumbnails/{asset.id}.jpg"
                target = settings.media_root / processed_relative
                subprocess.run(["ffmpeg", "-y", "-i", str(source), "-map", "0:v:0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)], check=True, capture_output=True, timeout=3600)
                subprocess.run(["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(target), "-frames:v", "1", str(settings.media_root / thumb_relative)], check=True, capture_output=True, timeout=120)
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(target)], check=True, capture_output=True, text=True, timeout=60)
                metadata = json.loads(probe.stdout); stream = next((item for item in metadata.get("streams", []) if "width" in item), {})
                asset.width, asset.height = stream.get("width"), stream.get("height")
                asset.duration_seconds = round(float(metadata.get("format", {}).get("duration", 0)))
                asset.processed_path, asset.thumbnail_path = processed_relative, thumb_relative
            else:
                raise ValueError("This media type is not supported.")
            asset.processing_state, asset.processing_error = "ready", None
        except Exception as exc:
            asset.processing_state, asset.processing_error = "failed", str(exc)[:1000]
        db.commit()
        return {"asset_id": asset.id, "status": asset.processing_state}
