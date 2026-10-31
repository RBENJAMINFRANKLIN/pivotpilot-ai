from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

# Keys that must never end up in audit details (they may carry resume or personal content).
_FORBIDDEN = {"text", "resume", "raw_text", "text_content", "password", "token", "response_text"}


def audit(
    db: Session,
    *,
    action: str,
    workspace_id: str | None,
    actor: str,
    user_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_hash: str | None = None,
) -> None:
    clean = {k: v for k, v in (details or {}).items() if k not in _FORBIDDEN}
    db.add(
        AuditLog(
            workspace_id=workspace_id,
            user_id=user_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=clean,
            ip_hash=ip_hash,
        )
    )
