from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import get_settings
from .routes import router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    for folder in (
        settings.media_root / "originals",
        settings.media_root / "processed",
        settings.media_root / "thumbnails",
        settings.backup_root,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz", tags=["operations"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": "api", "environment": settings.environment}


@app.get("/api/v1/system", tags=["operations"])
async def system_info() -> dict[str, str]:
    return {
        "application": settings.app_name,
        "media_root": str(settings.media_root),
        "backup_root": str(settings.backup_root),
    }
