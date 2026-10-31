from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import utcnow
from app.deps import DB, CtxDep
from app.errors import api_error
from app.models import ApplicationEvent, CareerTransition, Interview, InterviewEvaluation, JobApplication, ResumeVersion
from app.seed.interviews import RUBRIC, RUBRIC_VERSION
from app.services import applications as app_svc
from app.services import interviews as iv_svc
from app.services.audit import audit
from app.services.owned import check_version, get_owned
from app.services.scoring import skill_gaps

router = APIRouter(tags=["interviews & applications"])


# ----------------------------------------------------------------------------- interviews


def interview_out(db, iv: Interview) -> dict:
    evals = {e.question_id: e for e in db.scalars(select(InterviewEvaluation).where(InterviewEvaluation.interview_id == iv.id))}
    qs = []
    for qid in iv.question_ids:
        q = iv_svc.QUESTION_BY_ID[qid]
        e = evals.get(qid)
        qs.append({"id": qid, "text": q["text"], "type": q["type"], "competency": q["competency"],
                   "answer": e.response_text if e else None, "overall": e.overall if e else None,
                   "criteria": e.criterion_scores if e else None, "feedback": e.feedback if e else None, "method": e.method if e else None})
    return {"id": iv.id, "role": iv.role, "status": iv.status, "overall_score": iv.overall_score, "rubric": RUBRIC,
            "rubric_version": iv.rubric_version, "started_at": iv.started_at.isoformat(),
            "completed_at": iv.completed_at.isoformat() if iv.completed_at else None, "questions": qs}


@router.post("/transitions/{transition_id}/interviews", status_code=201)
def start_interview(transition_id: str, db: DB, ctx: CtxDep) -> dict:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    gaps = [g["skill_id"] for g in skill_gaps(db, t)["items"] if g["gap"] > 0]
    iv = Interview(workspace_id=ctx.workspace_id, transition_id=t.id, role=t.target_role,
                   question_ids=iv_svc.pick_questions(db, t, gaps), rubric_version=RUBRIC_VERSION)
    db.add(iv)
    db.commit()
    return interview_out(db, iv)


@router.get("/transitions/{transition_id}/interviews")
def list_interviews(transition_id: str, db: DB, ctx: CtxDep) -> list[dict]:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    return [{"id": i.id, "status": i.status, "overall_score": i.overall_score, "started_at": i.started_at.isoformat(),
             "questions": len(i.question_ids)}
            for i in db.scalars(select(Interview).where(Interview.transition_id == t.id).order_by(Interview.started_at.desc()))]


@router.get("/interviews/{interview_id}")
def get_interview(interview_id: str, db: DB, ctx: CtxDep) -> dict:
    return interview_out(db, get_owned(db, Interview, interview_id, ctx.workspace_id, "Interview"))


class InterviewAnswer(BaseModel):
    question_id: str
    response_text: str = Field(min_length=1, max_length=8000)


@router.post("/interviews/{interview_id}/answers")
def answer_interview(interview_id: str, body: InterviewAnswer, db: DB, ctx: CtxDep) -> dict:
    iv = get_owned(db, Interview, interview_id, ctx.workspace_id, "Interview")
    if iv.status != "in_progress":
        raise api_error(409, "INTERVIEW_CLOSED", "This interview is finished.")
    if body.question_id not in iv.question_ids:
        raise api_error(422, "UNKNOWN_QUESTION", "That question is not part of this interview.")
    if db.scalar(select(InterviewEvaluation).where(InterviewEvaluation.interview_id == iv.id, InterviewEvaluation.question_id == body.question_id)):
        raise api_error(409, "ALREADY_ANSWERED", "You already answered this question.")
    q = iv_svc.QUESTION_BY_ID[body.question_id]
    feedback, method, model = iv_svc.evaluate(db, workspace_id=ctx.workspace_id, is_guest=ctx.is_guest, question=q,
                                              answer=body.response_text, role=iv.role)
    db.add(InterviewEvaluation(workspace_id=ctx.workspace_id, interview_id=iv.id, question_id=q["id"], question_text=q["text"],
                               question_type=q["type"], response_text=body.response_text, criterion_scores=feedback["criteria"],
                               overall=iv_svc.overall(feedback["criteria"]), feedback=feedback, method=method, model_id=model,
                               prompt_version="interview-eval-v1"))
    db.flush()
    evals = list(db.scalars(select(InterviewEvaluation).where(InterviewEvaluation.interview_id == iv.id)))
    if len(evals) == len(iv.question_ids):
        iv.status, iv.completed_at = "completed", utcnow()
        iv.overall_score = round(sum(e.overall for e in evals) / len(evals), 1)
    db.commit()
    return interview_out(db, iv)


# ----------------------------------------------------------------------------- applications

Status = Literal["saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn", "no_response"]
Size = Literal["startup", "small", "medium", "large", "enterprise", "unknown"]


class ApplicationIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role_title: str = Field(min_length=1, max_length=200)
    role_category: str = Field(default="", max_length=80)
    company_size: Size = "unknown"
    source: str = Field(default="other", max_length=60)
    url: str | None = Field(default=None, max_length=2000, pattern=r"^https?://")
    resume_version_id: str | None = None
    status: Status = "saved"
    applied_at: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationPatch(BaseModel):
    status: Status | None = None
    status_note: str | None = Field(default=None, max_length=500)
    role_category: str | None = Field(default=None, max_length=80)
    company_size: Size | None = None
    source: str | None = Field(default=None, max_length=60)
    resume_version_id: str | None = None
    applied_at: date | None = None
    interview_date: date | None = None
    outcome: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=4000)
    version: int | None = None


def application_out(db, a: JobApplication) -> dict:
    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.occurred_at))
    return {"id": a.id, "company": a.company, "role_title": a.role_title, "role_category": a.role_category, "company_size": a.company_size,
            "source": a.source, "url": a.url, "resume_version_id": a.resume_version_id, "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None, "interview_dates": a.interview_dates, "outcome": a.outcome,
            "notes": a.notes, "version": a.version, "updated_at": a.updated_at.isoformat(),
            "history": [{"from": e.from_status, "to": e.to_status, "note": e.note, "at": e.occurred_at.isoformat()} for e in events]}


def create_application(db, ctx, body: ApplicationIn) -> JobApplication:
    if body.resume_version_id:
        get_owned(db, ResumeVersion, body.resume_version_id, ctx.workspace_id, "Resume")
    active = db.scalar(select(CareerTransition).where(CareerTransition.workspace_id == ctx.workspace_id, CareerTransition.is_active))
    a = JobApplication(workspace_id=ctx.workspace_id, transition_id=active.id if active else None,
                       **body.model_dump(exclude={"status", "role_category"}),
                       role_category=(body.role_category or body.role_title).strip().lower()[:80], status="saved")
    db.add(a)
    db.flush()
    db.add(ApplicationEvent(workspace_id=ctx.workspace_id, application_id=a.id, from_status=None, to_status="saved"))
    if body.status != "saved":
        app_svc.set_status(db, a, body.status)
    if a.status == "applied" and not a.applied_at:
        a.applied_at = date.today()
    audit(db, action="application.created", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="application", entity_id=a.id)
    return a


@router.post("/applications", status_code=201)
def add_application(body: ApplicationIn, db: DB, ctx: CtxDep) -> dict:
    a = create_application(db, ctx, body)
    db.commit()
    return application_out(db, a)


@router.get("/applications")
def list_applications(db: DB, ctx: CtxDep) -> list[dict]:
    return [application_out(db, a) for a in db.scalars(select(JobApplication).where(JobApplication.workspace_id == ctx.workspace_id)
                                                       .order_by(JobApplication.updated_at.desc()))]


@router.patch("/applications/{application_id}")
def patch_application(application_id: str, body: ApplicationPatch, db: DB, ctx: CtxDep) -> dict:
    a = get_owned(db, JobApplication, application_id, ctx.workspace_id, "Application")
    check_version(a, body.version)
    if body.resume_version_id:
        get_owned(db, ResumeVersion, body.resume_version_id, ctx.workspace_id, "Resume")
    if body.status:
        app_svc.set_status(db, a, body.status, body.status_note)
        if body.status == "applied" and not a.applied_at:
            a.applied_at = date.today()
    if body.interview_date:
        a.interview_dates = sorted({*a.interview_dates, body.interview_date.isoformat()})
    for k in ("role_category", "company_size", "source", "resume_version_id", "applied_at", "outcome", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(a, k, v.strip().lower() if k == "role_category" else v)
    db.commit()
    return application_out(db, a)


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: str, db: DB, ctx: CtxDep):
    db.delete(get_owned(db, JobApplication, application_id, ctx.workspace_id, "Application"))
    db.commit()


@router.get("/applications/analytics")
def application_analytics(db: DB, ctx: CtxDep) -> dict:
    return app_svc.analytics(db, ctx.workspace_id)
