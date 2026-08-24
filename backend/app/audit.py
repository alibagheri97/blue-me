from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    category: str,
    entity_type: str,
    entity_id: int | str | None,
    summary: str,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_username=actor.username if actor else "system",
        action=action,
        category=category,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    return entry

