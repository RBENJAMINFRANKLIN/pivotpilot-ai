from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.deps import ensure_user_workspace
from app.errors import api_error
from app.models import (
    OWNED_TABLES,
    CareerTransition,
    GuestMigration,
    Profile,
    ResumeVersion,
    User,
    Workspace,
)
from app.security.crypto import new_guest_token, token_hash
from app.services.audit import audit
from app.services.storage import get_storage


def create_guest_workspace(db: Session) -> tuple[Workspace, str]:
    token = new_guest_token()
    ws = Workspace(
        kind="guest",
        guest_token_hash=token_hash(token),
        expires_at=utcnow() + timedelta(days=get_settings().guest_retention_days),
    )
    db.add(ws)
    db.flush()
    db.add(Profile(workspace_id=ws.id))
    audit(db, action="guest.created", workspace_id=ws.id, actor="guest")
    db.commit()
    return ws, token


def migrate_guest_into_user(db: Session, guest_id: str, user: User) -> dict:
    """Atomically move every row of a guest workspace into the user's workspace.

    Safety: the guest row is locked, the GuestMigration unique constraint rejects a
    second import (including a concurrent one), and everything happens in one
    transaction, so a failure leaves both workspaces untouched."""
    guest = db.scalar(select(Workspace).where(Workspace.id == guest_id).with_for_update())
    if guest is None or guest.kind != "guest":
        raise api_error(404, "NOT_FOUND", "Guest workspace not found.")
    target = ensure_user_workspace(db, user)
    try:
        db.add(GuestMigration(guest_workspace_id=guest.id, target_workspace_id=target.id, user_id=user.id))
        db.flush()
    except IntegrityError:
        db.rollback()
        raise api_error(409, "ALREADY_IMPORTED", "This guest workspace has already been saved to an account.") from None

    try:
        # Keep exactly one active transition: the account's own active goal wins.
        if db.scalar(select(CareerTransition.id).where(CareerTransition.workspace_id == target.id, CareerTransition.is_active)):
            db.execute(update(CareerTransition).where(CareerTransition.workspace_id == guest.id).values(is_active=False))

        # Renumber guest resume versions after the account's latest (descending avoids clashes).
        offset = db.scalar(select(func.coalesce(func.max(ResumeVersion.version_number), 0)).where(ResumeVersion.workspace_id == target.id)) or 0
        if offset:
            for rv in db.scalars(select(ResumeVersion).where(ResumeVersion.workspace_id == guest.id).order_by(ResumeVersion.version_number.desc())):
                rv.version_number += offset
                db.flush()

        # Fill empty profile fields from the guest profile.
        gp = db.scalar(select(Profile).where(Profile.workspace_id == guest.id))
        tp = db.scalar(select(Profile).where(Profile.workspace_id == target.id))
        if gp and tp:
            for field in ("full_name", "employment_status", "current_role", "current_industry", "years_experience", "education", "location"):
                if getattr(tp, field) in (None, "") and getattr(gp, field) not in (None, ""):
                    setattr(tp, field, getattr(gp, field))
            if not tp.self_reported_skills and gp.self_reported_skills:
                tp.self_reported_skills = gp.self_reported_skills
            db.delete(gp)

        moved: dict[str, int] = {}
        for model in OWNED_TABLES:
            res = db.execute(update(model).where(model.workspace_id == guest.id).values(workspace_id=target.id))
            if res.rowcount:
                moved[model.__tablename__] = res.rowcount

        mig = db.scalar(select(GuestMigration).where(GuestMigration.guest_workspace_id == guest.id))
        mig.rows_moved = moved  # type: ignore[union-attr]
        audit(db, action="guest.migrated", workspace_id=target.id, actor="user", user_id=user.id,
              entity_type="workspace", entity_id=guest.id, details={"rows_moved": moved})
        db.delete(guest)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"target_workspace_id": target.id, "rows_moved": moved}


def delete_workspace_data(db: Session, ws: Workspace, actor: str, user: User | None) -> None:
    storage = get_storage()
    for key in db.scalars(select(ResumeVersion.storage_key).where(ResumeVersion.workspace_id == ws.id, ResumeVersion.storage_key.is_not(None))):
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001 - a missing file must not block deletion of the rest
            pass
    audit(db, action="workspace.deleted", workspace_id=ws.id, actor=actor, user_id=user.id if user else None)
    db.delete(ws)
    if user:
        db.delete(user)
    db.commit()


def cleanup_expired_guests(db: Session) -> int:
    expired = list(db.scalars(select(Workspace).where(Workspace.kind == "guest", Workspace.expires_at < utcnow())))
    for ws in expired:
        delete_workspace_data(db, ws, actor="system", user=None)
    return len(expired)
