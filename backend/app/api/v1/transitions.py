from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update

from app.config import get_settings
from app.db import utcnow
from app.deps import DB, CtxDep
from app.errors import api_error
from app.models import CareerTransition, Profile
from app.services.audit import audit
from app.services.owned import check_version, get_owned

router = APIRouter(tags=["career transitions"])

Format = Literal["video", "reading", "interactive", "practice", "project"]
EmploymentStatus = Literal["employed", "unemployed", "student", "self_employed", "career_break", "other"]


def _future_date(v: date | None) -> date | None:
    if v is not None and v <= date.today():
        raise ValueError("Deadline must be in the future")
    return v


class SelfSkill(BaseModel):
    skill_id: str = Field(max_length=80)
    level: int = Field(ge=1, le=5)  # 1 = never used ... 5 = use it confidently at work


class TransitionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    target_role: str = Field(min_length=2, max_length=160)
    current_role: str | None = Field(default=None, max_length=160)
    current_industry: str | None = Field(default=None, max_length=160)
    employment_status: EmploymentStatus | None = None
    target_location: str | None = Field(default=None, max_length=160)
    deadline: date | None = None
    weekly_hours: float = Field(default=6, ge=1, le=80)
    study_days_per_week: int = Field(default=5, ge=1, le=7)
    budget_amount: float | None = Field(default=None, ge=0, le=1_000_000)
    budget_currency: str = Field(default="USD", min_length=3, max_length=3)
    learning_formats: list[Format] = Field(default_factory=list)
    language: str = Field(default="en", max_length=20)

    @field_validator("deadline")
    @classmethod
    def _future(cls, v: date | None) -> date | None:
        return _future_date(v)


class TransitionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    target_role: str | None = Field(default=None, min_length=2, max_length=160)
    current_role: str | None = Field(default=None, max_length=160)
    current_industry: str | None = Field(default=None, max_length=160)
    employment_status: EmploymentStatus | None = None
    target_location: str | None = Field(default=None, max_length=160)
    deadline: date | None = None
    weekly_hours: float | None = Field(default=None, ge=1, le=80)
    study_days_per_week: int | None = Field(default=None, ge=1, le=7)
    budget_amount: float | None = Field(default=None, ge=0, le=1_000_000)
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    learning_formats: list[Format] | None = None
    language: str | None = Field(default=None, max_length=20)
    version: int | None = None

    @field_validator("deadline")
    @classmethod
    def _future(cls, v: date | None) -> date | None:
        return _future_date(v)


class TransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    target_role: str
    current_role: str | None
    current_industry: str | None
    employment_status: str | None
    target_location: str | None
    deadline: date | None
    weekly_hours: float
    study_days_per_week: int
    budget_amount: float | None
    budget_currency: str
    learning_formats: list[str]
    language: str
    is_active: bool
    archived_at: str | None = None
    version: int

    @field_validator("archived_at", mode="before")
    @classmethod
    def _iso(cls, v):
        return v.isoformat() if v else None


@router.get("/transitions", response_model=list[TransitionOut])
def list_transitions(db: DB, ctx: CtxDep):
    return db.scalars(select(CareerTransition).where(CareerTransition.workspace_id == ctx.workspace_id)
                      .order_by(CareerTransition.is_active.desc(), CareerTransition.created_at.desc())).all()


@router.post("/transitions", response_model=TransitionOut, status_code=201)
def create_transition(body: TransitionIn, db: DB, ctx: CtxDep):
    count = db.scalar(select(func.count(CareerTransition.id)).where(CareerTransition.workspace_id == ctx.workspace_id)) or 0
    if ctx.is_guest and count >= get_settings().guest_max_transitions:
        raise api_error(403, "GUEST_LIMIT", "Guest workspaces can hold a limited number of goals. Save your progress to an account to add more.")
    t = CareerTransition(workspace_id=ctx.workspace_id, **body.model_dump())
    t.budget_currency = t.budget_currency.upper()
    has_active = db.scalar(select(CareerTransition.id).where(CareerTransition.workspace_id == ctx.workspace_id, CareerTransition.is_active))
    t.is_active = not has_active
    db.add(t)
    prof = db.scalar(select(Profile).where(Profile.workspace_id == ctx.workspace_id))
    if prof:
        prof.current_role = prof.current_role or body.current_role
        prof.current_industry = prof.current_industry or body.current_industry
        prof.employment_status = prof.employment_status or body.employment_status
    audit(db, action="transition.created", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="transition", entity_id=t.id)
    db.commit()
    return t


@router.get("/transitions/{transition_id}", response_model=TransitionOut)
def get_transition(transition_id: str, db: DB, ctx: CtxDep):
    return get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")


@router.patch("/transitions/{transition_id}", response_model=TransitionOut)
def patch_transition(transition_id: str, body: TransitionPatch, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    check_version(t, body.version)
    for k, v in body.model_dump(exclude_unset=True, exclude={"version"}).items():
        setattr(t, k, v.upper() if k == "budget_currency" and v else v)
    audit(db, action="transition.updated", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="transition",
          entity_id=t.id, details={"fields": sorted(body.model_dump(exclude_unset=True, exclude={"version"}))})
    db.commit()
    return t


@router.post("/transitions/{transition_id}/activate", response_model=TransitionOut)
def activate_transition(transition_id: str, db: DB, ctx: CtxDep):
    """Switch the active goal. Other goals keep all their history; they are just inactive."""
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    if t.archived_at:
        raise api_error(409, "ARCHIVED", "Restore this goal before making it active.")
    db.execute(update(CareerTransition).where(CareerTransition.workspace_id == ctx.workspace_id, CareerTransition.id != t.id)
               .values(is_active=False))
    db.flush()
    t.is_active = True
    audit(db, action="transition.activated", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="transition", entity_id=t.id)
    db.commit()
    return t


@router.post("/transitions/{transition_id}/archive", response_model=TransitionOut)
def archive_transition(transition_id: str, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    t.archived_at = utcnow()
    t.is_active = False
    db.commit()
    return t


@router.post("/transitions/{transition_id}/restore", response_model=TransitionOut)
def restore_transition(transition_id: str, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    t.archived_at = None
    db.commit()
    return t


class ProfileIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    full_name: str | None = Field(default=None, max_length=120)
    employment_status: EmploymentStatus | None = None
    current_role: str | None = Field(default=None, max_length=160)
    current_industry: str | None = Field(default=None, max_length=160)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    education: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=160)
    preferred_formats: list[Format] = Field(default_factory=list)
    language: str = Field(default="en", max_length=20)
    self_reported_skills: list[SelfSkill] = Field(default_factory=list, max_length=60)


@router.get("/profile", response_model=ProfileIO)
def get_profile(db: DB, ctx: CtxDep):
    return db.scalar(select(Profile).where(Profile.workspace_id == ctx.workspace_id))


@router.put("/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, db: DB, ctx: CtxDep):
    from app.services.evidence import record_self_reported

    prof = db.scalar(select(Profile).where(Profile.workspace_id == ctx.workspace_id))
    for k, v in body.model_dump().items():
        setattr(prof, k, v)
    record_self_reported(db, ctx.workspace_id, [s.model_dump() for s in body.self_reported_skills])
    db.commit()
    return prof
