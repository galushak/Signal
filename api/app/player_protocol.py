"""Device-only protocol helpers.

The management preview remains a human-facing representation.  This module
builds the independent, cacheable manifest consumed by a Signal Player.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Content, ContentAssignment, ContentVersion, Layout, MediaAsset, Player, Zone
from .settings import get_settings

MANIFEST_SCHEMA = 1


def _asset_ids(value: Any) -> set[str]:
    """Find known media references without treating arbitrary URLs as assets."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"assetId", "asset_id", "mediaId", "media_id"} and isinstance(item, str):
                found.add(item)
            found.update(_asset_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_asset_ids(item))
    return found


def _checksum(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assignment_data(item: ContentAssignment) -> dict:
    return {
        "id": item.id,
        "destinationType": item.destination_type,
        "destinationId": item.destination_id,
        "enabled": item.enabled,
        "priority": item.priority,
        "position": item.position,
        "durationSeconds": item.duration_seconds or 20,
        "transition": item.transition or "none",
        "startsAt": item.starts_at.isoformat() if item.starts_at else None,
        "endsAt": item.ends_at.isoformat() if item.ends_at else None,
        "weekdays": item.weekdays,
        "dailyStart": item.daily_start,
        "dailyEnd": item.daily_end,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
    }


def build_manifest(player: Player, db: Session) -> dict:
    """Build one complete desired state. It deliberately includes schedules,
    including currently inactive assignments, so playback remains correct offline.
    """
    settings = get_settings()
    layout = db.get(Layout, player.layout_id) if player.layout_id else None
    zones = [] if not layout else sorted((zone for zone in layout.zones if zone.enabled), key=lambda zone: (zone.z_index, zone.name))
    destinations = {player.id, *(zone.id for zone in zones)}
    content_items: list[dict] = []
    asset_ids: set[str] = set()
    assignments = db.scalars(select(ContentAssignment).where(ContentAssignment.destination_id.in_(destinations))).all()
    for assignment in assignments:
        if assignment.source_type == "media" and assignment.media_asset_id:
            asset = db.get(MediaAsset, assignment.media_asset_id)
            if not asset or asset.trashed_at:
                continue
            asset_ids.add(asset.id)
            content_items.append({
                "id": assignment.id,
                "name": asset.display_name,
                "source": {"type": asset.media_type, "assetId": asset.id, "fit": "contain"},
                "assignment": _assignment_data(assignment),
            })
            continue
        content = db.get(Content, assignment.content_id) if assignment.content_id else None
        version = db.scalar(select(ContentVersion).where(ContentVersion.content_id == assignment.content_id, ContentVersion.state == "published")) if assignment.content_id else None
        if not content or not version or content.trashed_at:
            continue
        document = version.design_document or {}
        asset_ids.update(_asset_ids(document))
        content_items.append({
            "id": content.id,
            "name": content.name,
            "revision": version.revision,
            "source": {"type": "design"},
            "design": document,
            "assignment": _assignment_data(assignment),
        })
    media = []
    for asset_id in sorted(asset_ids):
        asset = db.get(MediaAsset, asset_id)
        if not asset or asset.trashed_at:
            continue
        relative = asset.processed_path or asset.original_path
        path = settings.media_root / relative
        checksum = _checksum(path)
        if not checksum:
            continue
        media.append({"assetId": asset.id, "path": f"/api/v1/player-agent/media/{asset.id}", "sha256": checksum, "size": path.stat().st_size, "mimeType": asset.mime_type, "filename": Path(relative).name})
    payload = {
        "schemaVersion": MANIFEST_SCHEMA,
        "playerId": player.id,
        "generatedAt": datetime.now(UTC).isoformat(),
        "timezone": settings.player_timezone,
        "display": {"logicalWidth": 1920, "logicalHeight": 1080, "resolution": player.resolution or "1920x1080"},
        "layout": None if not layout else {"id": layout.id, "name": layout.name, "version": layout.updated_at.isoformat() if layout.updated_at else None, "canvas": {"width": layout.logical_width, "height": layout.logical_height}, "zones": [{"id": zone.id, "name": zone.name, "x": zone.x, "y": zone.y, "width": zone.width, "height": zone.height, "zIndex": zone.z_index, "background": zone.background, "border": zone.border, "padding": zone.padding} for zone in zones]},
        "content": sorted(content_items, key=lambda item: (item["assignment"]["destinationId"], item["assignment"]["position"], item["assignment"]["createdAt"] if item["assignment"].get("createdAt") else "", item["id"])),
        "media": media,
    }
    # generatedAt is observability metadata, not a desired-state change.
    revision_payload = {key: value for key, value in payload.items() if key != "generatedAt"}
    canonical = json.dumps(revision_payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    payload["revision"] = hashlib.sha256(canonical).hexdigest()
    return payload


def media_is_allowed(asset_id: str, player: Player, db: Session) -> MediaAsset | None:
    manifest = build_manifest(player, db)
    return db.get(MediaAsset, asset_id) if any(entry["assetId"] == asset_id for entry in manifest["media"]) else None
