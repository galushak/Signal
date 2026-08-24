from typing import Any

from sqlalchemy.orm import Session

from .models import AuditEvent, User


def record(db: Session, *, actor: User | None, action: str, resource_type: str, resource_id: str | None = None, resource_name: str | None = None, scope_type: str | None = None, scope_id: str | None = None, source_ip: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    db.add(AuditEvent(user_id=actor.id if actor else None, action=action, resource_type=resource_type, resource_id=resource_id, resource_name=resource_name, scope_type=scope_type, scope_id=scope_id, source_ip=source_ip, metadata_json=metadata))
