from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import api_error, not_found
from app.models import CareerTransition

M = TypeVar("M")


def get_owned(db: Session, model: type[M], obj_id: str, workspace_id: str, what: str = "Item") -> M:
    """Fetch a row only if it belongs to the caller's workspace (404 otherwise)."""
    obj = db.scalar(select(model).where(model.id == obj_id, model.workspace_id == workspace_id))  # type: ignore[attr-defined]
    if obj is None:
        raise not_found(what)
    return obj


def active_transition(db: Session, workspace_id: str) -> CareerTransition:
    t = db.scalar(select(CareerTransition).where(CareerTransition.workspace_id == workspace_id, CareerTransition.is_active))
    if t is None:
        raise api_error(409, "NO_ACTIVE_TRANSITION", "Create or select a career goal first.")
    return t


def check_version(obj, expected: int | None) -> None:
    """Optimistic concurrency: reject writes based on a stale copy."""
    if expected is not None and getattr(obj, "version", None) != expected:
        raise api_error(409, "STALE_VERSION", "This item changed in another tab. Reload and try again.")
    if hasattr(obj, "version"):
        obj.version += 1
