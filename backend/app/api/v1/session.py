from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.config import get_settings
from app.db import as_utc, utcnow
from app.deps import AUTH_COOKIE, DB, GUEST_COOKIE, Ctx, CtxDep, OptionalCtxDep, ensure_user_workspace, resolve_guest
from app.errors import api_error
from app.models import User
from app.security.crypto import hash_password, ip_hash, issue_local_token, verify_password
from app.security.ratelimit import client_ip, enforce
from app.services.audit import audit
from app.services.workspaces import create_guest_workspace, delete_workspace_data, migrate_guest_into_user

router = APIRouter(tags=["session"])


class SessionOut(BaseModel):
    kind: str
    workspace_id: str
    user_email: str | None = None
    display_name: str | None = None
    expires_at: str | None = None
    retention_notice: str
    limits: dict


def _session_out(ctx: Ctx) -> SessionOut:
    s = get_settings()
    if ctx.is_guest:
        exp = as_utc(ctx.workspace.expires_at)
        notice = (
            f"Guest workspace: your work is stored on our server for {s.guest_retention_days} days after it was created "
            "and is tied to this browser. Use Save My Progress to keep it permanently."
        )
        limits = {"transitions": s.guest_max_transitions, "resume_versions": s.guest_max_resume_versions,
                  "ai_calls_per_day": s.guest_daily_ai_calls, "upload_mb": s.max_upload_bytes // (1024 * 1024)}
        return SessionOut(kind="guest", workspace_id=ctx.workspace_id, expires_at=exp.isoformat() if exp else None,
                          retention_notice=notice, limits=limits)
    return SessionOut(kind="user", workspace_id=ctx.workspace_id, user_email=ctx.user.email,  # type: ignore[union-attr]
                      display_name=ctx.user.display_name,  # type: ignore[union-attr]
                      retention_notice="Your work is saved to your account until you delete it.",
                      limits={"ai_calls_per_day": s.user_daily_ai_calls, "upload_mb": s.max_upload_bytes // (1024 * 1024)})


def _set_cookie(resp: Response, name: str, value: str, max_age: int) -> None:
    s = get_settings()
    resp.set_cookie(name, value, max_age=max_age, httponly=True, secure=s.cookie_secure, samesite="lax", path="/")


@router.get("/config")
def public_config() -> dict:
    s = get_settings()
    return {
        "auth_mode": s.auth_mode,
        "supabase_url": s.supabase_url if s.auth_mode == "supabase" else None,
        "supabase_anon_key": s.supabase_anon_key if s.auth_mode == "supabase" else None,
        "guest_retention_days": s.guest_retention_days,
        "ai_provider": s.ai_provider,
        "demo_mode_enabled": s.demo_mode_enabled,
        "resume_sent_to_hosted_ai": s.ai_provider == "anthropic" and s.ai_send_resume_to_hosted,
    }


@router.get("/session", response_model=SessionOut | None)
def get_session(ctx: OptionalCtxDep):
    return _session_out(ctx) if ctx else None


@router.post("/session/guest", response_model=SessionOut)
def start_guest(request: Request, response: Response, db: DB, ctx: OptionalCtxDep):
    if ctx:
        return _session_out(ctx)
    enforce(request, "guest_create", get_settings().rate_limit_guest_create_per_hour, 3600)
    ws, token = create_guest_workspace(db)
    _set_cookie(response, GUEST_COOKIE, token, get_settings().guest_retention_days * 86400)
    return _session_out(Ctx(workspace=ws, user=None))


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


def _require_local():
    if get_settings().auth_mode != "local":
        raise api_error(400, "USE_SUPABASE", "Sign-in is handled by Supabase in this deployment.")


@router.post("/auth/register", dependencies=[Depends(_require_local)])
def register(body: RegisterIn, request: Request, response: Response, db: DB) -> dict:
    enforce(request, "auth", get_settings().rate_limit_auth_per_minute)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise api_error(409, "EMAIL_TAKEN", "An account with this email already exists. Try signing in.")
    user = User(auth_provider="local", email=email, password_hash=hash_password(body.password), display_name=body.display_name)
    db.add(user)
    db.flush()
    ensure_user_workspace(db, user)
    audit(db, action="user.registered", workspace_id=None, actor="user", user_id=user.id, ip_hash=ip_hash(client_ip(request)))
    db.commit()
    token = issue_local_token(user.id)
    _set_cookie(response, AUTH_COOKIE, token, get_settings().access_token_ttl_minutes * 60)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/login", dependencies=[Depends(_require_local)])
def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict:
    enforce(request, "auth", get_settings().rate_limit_auth_per_minute)
    user = db.scalar(select(User).where(User.email == body.email.lower(), User.auth_provider == "local"))
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise api_error(401, "BAD_CREDENTIALS", "Email or password is incorrect.")
    user.last_login_at = utcnow()
    audit(db, action="user.login", workspace_id=None, actor="user", user_id=user.id, ip_hash=ip_hash(client_ip(request)))
    db.commit()
    token = issue_local_token(user.id)
    _set_cookie(response, AUTH_COOKIE, token, get_settings().access_token_ttl_minutes * 60)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}


@router.post("/auth/migrate-guest")
def migrate_guest(request: Request, response: Response, db: DB, ctx: CtxDep) -> dict:
    """Save My Progress: import the guest workspace in this browser into the signed-in account."""
    if ctx.is_guest:
        raise api_error(401, "SIGN_IN_REQUIRED", "Create an account or sign in first.")
    guest = resolve_guest(db, request)
    if guest is None:
        raise api_error(404, "NO_GUEST_WORKSPACE", "There is no guest workspace in this browser to import.")
    result = migrate_guest_into_user(db, guest.id, ctx.user)  # type: ignore[arg-type]
    response.delete_cookie(GUEST_COOKIE, path="/")
    return {"ok": True, **result}


@router.delete("/workspace")
def delete_everything(response: Response, db: DB, ctx: CtxDep, confirm: Annotated[str, "must equal DELETE"] = "") -> dict:
    if confirm != "DELETE":
        raise api_error(400, "CONFIRMATION_REQUIRED", "Pass confirm=DELETE to permanently delete all your data.")
    delete_workspace_data(db, ctx.workspace, actor=ctx.actor, user=ctx.user)
    response.delete_cookie(GUEST_COOKIE, path="/")
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}
