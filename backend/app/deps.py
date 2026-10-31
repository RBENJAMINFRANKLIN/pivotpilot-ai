"""Request context: who is calling and which workspace they own.

Resolution order: Bearer token (Supabase or local JWT) > local auth cookie > guest cookie.
Every data endpoint depends on `get_ctx`, and every query is filtered by ctx.workspace_id.
"""

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import as_utc, get_db, utcnow
from app.errors import api_error
from app.models import Profile, User, Workspace
from app.security.crypto import decode_local_token, token_hash

GUEST_COOKIE = "pp_guest"
AUTH_COOKIE = "pp_auth"

DB = Annotated[Session, Depends(get_db)]


@dataclass
class Ctx:
    workspace: Workspace
    user: User | None

    @property
    def workspace_id(self) -> str:
        return self.workspace.id

    @property
    def actor(self) -> str:
        return "user" if self.user else "guest"

    @property
    def is_guest(self) -> bool:
        return self.user is None


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def verify_supabase_token(token: str) -> dict | None:
    s = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            if not s.supabase_jwt_secret:
                return None
            key: object = s.supabase_jwt_secret
            algs = ["HS256"]
        else:
            key = _jwks_client(f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token).key
            algs = ["RS256", "ES256"]
        return jwt.decode(token, key, algorithms=algs, audience="authenticated")  # type: ignore[arg-type]
    except (jwt.PyJWTError, OSError):
        return None


def ensure_user_workspace(db: Session, user: User) -> Workspace:
    ws = db.scalar(select(Workspace).where(Workspace.owner_user_id == user.id))
    if ws:
        return ws
    ws = Workspace(kind="user", owner_user_id=user.id)
    db.add(ws)
    db.flush()
    db.add(Profile(workspace_id=ws.id, full_name=user.display_name))
    db.flush()
    return ws


def resolve_user(db: Session, request: Request) -> User | None:
    s = get_settings()
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if token and s.auth_mode == "supabase":
        claims = verify_supabase_token(token)
        if not claims:
            raise api_error(401, "INVALID_TOKEN", "Your sign-in has expired. Please sign in again.")
        user = db.scalar(select(User).where(User.external_id == claims["sub"]))
        if not user:
            email = (claims.get("email") or f"{claims['sub']}@users.supabase").lower()
            user = User(auth_provider="supabase", external_id=claims["sub"], email=email)
            db.add(user)
            db.flush()
        return user
    token = token or request.cookies.get(AUTH_COOKIE)
    if token and s.auth_mode == "local":
        uid = decode_local_token(token)
        if not uid:
            raise api_error(401, "INVALID_TOKEN", "Your sign-in has expired. Please sign in again.")
        return db.get(User, uid)
    return None


def resolve_guest(db: Session, request: Request) -> Workspace | None:
    raw = request.cookies.get(GUEST_COOKIE)
    if not raw:
        return None
    ws = db.scalar(select(Workspace).where(Workspace.guest_token_hash == token_hash(raw), Workspace.kind == "guest"))
    if not ws:
        return None
    if ws.expires_at and as_utc(ws.expires_at) < utcnow():  # type: ignore[operator]
        return None
    return ws


def get_optional_ctx(request: Request, db: DB) -> Ctx | None:
    user = resolve_user(db, request)
    if user:
        ws = ensure_user_workspace(db, user)
        _touch(db, ws)
        return Ctx(workspace=ws, user=user)
    guest = resolve_guest(db, request)
    if guest:
        _touch(db, guest)
        return Ctx(workspace=guest, user=None)
    return None


def get_ctx(ctx: Annotated[Ctx | None, Depends(get_optional_ctx)]) -> Ctx:
    if ctx is None:
        raise api_error(401, "NO_SESSION", "Start as a guest or sign in to continue.")
    return ctx


def _touch(db: Session, ws: Workspace) -> None:
    now = utcnow()
    if now - as_utc(ws.last_seen_at) > timedelta(minutes=5):  # type: ignore[operator]
        ws.last_seen_at = now
        db.commit()


CtxDep = Annotated[Ctx, Depends(get_ctx)]
OptionalCtxDep = Annotated[Ctx | None, Depends(get_optional_ctx)]
