from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, Ctx, CtxDep
from app.models import AssessmentAttempt, AssessmentBlueprint, AssessmentQuestion, CareerTransition
from app.security.ratelimit import enforce
from app.services import assessment as engine
from app.services import planning
from app.services.audit import audit
from app.services.owned import get_owned

router = APIRouter(tags=["assessments"])


class StartIn(BaseModel):
    kind: Literal["diagnostic", "topic_check"] = "diagnostic"
    skill_id: str | None = None
    timed: bool = False
    seconds_per_question: int | None = Field(default=None, ge=20, le=600)


class AnswerIn(BaseModel):
    question_id: str
    response: Any = None


def _view(db, attempt: AssessmentAttempt) -> dict:
    bp = db.get(AssessmentBlueprint, attempt.blueprint_id)
    q = db.get(AssessmentQuestion, attempt.current_question_id) if attempt.current_question_id else None
    return {
        "id": attempt.id, "transition_id": attempt.transition_id, "kind": attempt.kind, "status": attempt.status,
        "timed": attempt.timed, "seconds_per_question": attempt.seconds_per_question, "time_left": engine.time_left(attempt),
        "question": engine.public_question(q) if q else None,
        "progress": engine.coverage(attempt, bp),
        "blueprint": {"items": [{k: i[k] for k in ("skill_id", "name", "importance", "min_questions")} for i in bp.items],
                      "uncovered": bp.uncovered, "budget": bp.question_budget, "engine_version": bp.engine_version},
        "results": attempt.results, "started_at": attempt.started_at, "completed_at": attempt.completed_at,
    }


def _after_completion(db, attempt: AssessmentAttempt, ctx: Ctx) -> None:
    """Quiz results feed straight back into the plan when they justify a change."""
    db.flush()
    revision = planning.maybe_revise(db, db.get(CareerTransition, attempt.transition_id), attempt)
    attempt.results = {**(attempt.results or {}), "plan_revision": revision}
    audit(db, action="assessment.completed", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="assessment",
          entity_id=attempt.id, details={"plan_revised": bool(revision)})


def _advance(db, attempt: AssessmentAttempt, ctx: Ctx) -> None:
    bp = db.get(AssessmentBlueprint, attempt.blueprint_id)
    nxt = engine.select_next(db, attempt, bp)
    if nxt is None:
        engine.finish(db, attempt, bp, force=True)
        _after_completion(db, attempt, ctx)
    else:
        engine.serve(db, attempt, nxt)


@router.post("/transitions/{transition_id}/assessments", status_code=201)
def start(transition_id: str, body: StartIn, request: Request, db: DB, ctx: CtxDep) -> dict:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    existing = db.scalar(select(AssessmentAttempt).where(
        AssessmentAttempt.transition_id == t.id, AssessmentAttempt.status == "in_progress", AssessmentAttempt.kind == body.kind))
    if existing and (body.kind == "diagnostic" or existing.state.get("skill_id") == body.skill_id):
        return _view(db, existing)  # resume rather than start a duplicate
    enforce(request, "ai", get_settings().rate_limit_ai_per_minute, subject=ctx.workspace_id)
    bp = engine.build_blueprint(db, t, is_guest=ctx.is_guest, kind=body.kind, skill_id=body.skill_id)
    attempt = AssessmentAttempt(workspace_id=ctx.workspace_id, transition_id=t.id, blueprint_id=bp.id, kind=body.kind,
                                timed=body.timed, seconds_per_question=(body.seconds_per_question or 90) if body.timed else None,
                                state={"asked": [], "skills": {}, "skill_id": body.skill_id})
    db.add(attempt)
    db.flush()
    _advance(db, attempt, ctx)
    audit(db, action="assessment.started", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="assessment",
          entity_id=attempt.id, details={"kind": body.kind, "budget": bp.question_budget})
    db.commit()
    return _view(db, attempt)


@router.get("/transitions/{transition_id}/assessments")
def history(transition_id: str, db: DB, ctx: CtxDep) -> list[dict]:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    rows = db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.transition_id == t.id).order_by(AssessmentAttempt.started_at.desc()))
    return [{"id": a.id, "kind": a.kind, "status": a.status, "started_at": a.started_at, "completed_at": a.completed_at,
             "skill_id": a.state.get("skill_id"), "overall": (a.results or {}).get("overall")} for a in rows]


@router.get("/assessments/{attempt_id}")
def get_attempt(attempt_id: str, db: DB, ctx: CtxDep) -> dict:
    return _view(db, get_owned(db, AssessmentAttempt, attempt_id, ctx.workspace_id, "Assessment"))


@router.post("/assessments/{attempt_id}/answer")
def submit_answer(attempt_id: str, body: AnswerIn, db: DB, ctx: CtxDep) -> dict:
    attempt = get_owned(db, AssessmentAttempt, attempt_id, ctx.workspace_id, "Assessment")
    engine.answer(db, attempt, body.question_id, body.response, is_guest=ctx.is_guest)
    _advance(db, attempt, ctx)
    db.commit()
    # Deliberately no correctness feedback here: answers are revealed in the review after finishing.
    return {"recorded": True, **_view(db, attempt)}


@router.post("/assessments/{attempt_id}/finish")
def finish_attempt(attempt_id: str, db: DB, ctx: CtxDep) -> dict:
    attempt = get_owned(db, AssessmentAttempt, attempt_id, ctx.workspace_id, "Assessment")
    if attempt.status == "in_progress":
        engine.finish(db, attempt, db.get(AssessmentBlueprint, attempt.blueprint_id))
        _after_completion(db, attempt, ctx)
        db.commit()
    return _view(db, attempt)


@router.get("/assessments/{attempt_id}/review")
def review(attempt_id: str, db: DB, ctx: CtxDep) -> list[dict]:
    attempt = get_owned(db, AssessmentAttempt, attempt_id, ctx.workspace_id, "Assessment")
    return engine.review(db, attempt)
