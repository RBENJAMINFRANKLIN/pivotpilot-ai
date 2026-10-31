from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings
from app.deps import DB, CtxDep
from app.errors import api_error
from app.models import CareerTransition, JobDescription, JobRequirement, ResumeAnalysis, ResumeVersion
from app.security.ratelimit import enforce
from app.services import jobs as jobs_svc
from app.services import scoring
from app.services.audit import audit
from app.services.evidence import latest_resume
from app.services.owned import get_owned

router = APIRouter(tags=["job analysis"])


class JobIn(BaseModel):
    mode: Literal["url", "paste", "role"]
    url: str | None = Field(default=None, max_length=2000)
    text: str | None = Field(default=None, max_length=40000)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check(self):
        if self.mode == "url" and not self.url:
            raise ValueError("url is required for mode=url")
        if self.mode == "paste" and (not self.text or len(self.text.strip()) < 100):
            raise ValueError("Paste at least a few sentences of the job description (100+ characters)")
        return self


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    label: str
    category: str
    importance: str
    skill_id: str | None
    source_excerpt: str | None
    source_url: str | None
    confidence: float
    min_years: float | None
    prerequisite_skill_ids: list[str]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source_type: str
    source_url: str | None
    title: str | None
    company: str | None
    fetch_status: str
    analysis_method: str | None
    created_at: datetime
    requirements: list[RequirementOut]


class JobIntakeResult(BaseModel):
    status: str  # ok | needs_paste
    message: str
    job: JobOut | None = None


def _save_job(db, ctx, t: CareerTransition, *, text: str, source_type: str, url: str | None, title: str | None,
              company: str | None, cmap: jobs_svc.CompetencyMap, method: str, model: str | None) -> JobDescription:
    job = JobDescription(workspace_id=ctx.workspace_id, transition_id=t.id, source_type=source_type, source_url=url,
                         title=title or t.target_role, company=company, raw_text=text, fetch_status="ok",
                         analysis_method=method, model_id=model, prompt_version=jobs_svc.PROMPT_VERSION)
    for i, r in enumerate(cmap.requirements):
        job.requirements.append(JobRequirement(workspace_id=ctx.workspace_id, position=i, source_url=url, **r.model_dump()))
    db.add(job)
    audit(db, action="job.analyzed", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="job", entity_id=job.id,
          details={"source_type": source_type, "requirements": len(cmap.requirements), "method": method})
    db.commit()
    return job


@router.post("/transitions/{transition_id}/job", response_model=JobIntakeResult)
def set_job(transition_id: str, body: JobIn, request: Request, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    enforce(request, "ai", get_settings().rate_limit_ai_per_minute, subject=ctx.workspace_id)
    if body.mode == "role":
        cmap = jobs_svc.role_template_map(t.target_role)
        if cmap is None:
            return JobIntakeResult(status="needs_paste", message=f"We do not have a template for '{t.target_role}'. Paste a job description so we can work from real requirements.")
        job = _save_job(db, ctx, t, text="", source_type="role_only", url=None, title=t.target_role, company=None, cmap=cmap,
                        method="role_template", model=None)
        return JobIntakeResult(status="ok", message="Using a typical requirement template for this role. Paste a real job description for evidence-backed requirements.", job=job)
    text, url, title, company = body.text or "", None, body.title, body.company
    if body.mode == "url":
        fetched = jobs_svc.fetch_job(body.url)  # type: ignore[arg-type]
        audit(db, action="job.fetch", workspace_id=ctx.workspace_id, actor=ctx.actor, details={"status": fetched.status})
        db.commit()
        if fetched.status != "ok":
            return JobIntakeResult(status="needs_paste", message=fetched.message)
        text, url, title, company = fetched.text, fetched.url, title or fetched.title, company or fetched.company
    cmap, result = jobs_svc.analyze(db, workspace_id=ctx.workspace_id, is_guest=ctx.is_guest, text=text)
    if not [r for r in cmap.requirements if r.skill_id]:
        db.commit()
        return JobIntakeResult(status="needs_paste", message="We could not find recognisable skill requirements in that text. Check it is the full job description.")
    job = _save_job(db, ctx, t, text=text, source_type=body.mode, url=url, title=title, company=company, cmap=cmap,
                    method=f"{result.method}:{result.provider}" if result else "rules", model=result.model if result else None)
    return JobIntakeResult(status="ok", message="Job requirements extracted.", job=job)


@router.get("/transitions/{transition_id}/job", response_model=JobOut | None)
def get_job(transition_id: str, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    return scoring.current_job(db, t.id)


class AnalysisIn(BaseModel):
    resume_version_id: str | None = None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    resume_version_id: str
    job_description_id: str
    quality_score: float
    quality_breakdown: dict
    fit_score: float | None
    fit_breakdown: dict
    requirement_evidence: list[dict]
    transferable_skills: list[dict]
    suggestions: list[dict]
    experience_alignment: dict
    scoring_version: str
    created_at: datetime


@router.post("/transitions/{transition_id}/analysis", response_model=AnalysisOut, status_code=201)
def run_analysis(transition_id: str, body: AnalysisIn, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    rv = (get_owned(db, ResumeVersion, body.resume_version_id, ctx.workspace_id, "Resume") if body.resume_version_id
          else latest_resume(db, ctx.workspace_id))
    if rv is None:
        raise api_error(409, "NO_RESUME", "Add your resume or career details first.")
    job = scoring.current_job(db, t.id)
    if job is None:
        raise api_error(409, "NO_JOB", "Add a target job description first.")
    ex = rv.extracted
    q_score, q_parts = scoring.resume_quality(ex)
    evidence = scoring.requirement_evidence(job.requirements, ex)
    f_score, f_parts = scoring.fit_score(evidence)
    a = ResumeAnalysis(workspace_id=ctx.workspace_id, transition_id=t.id, resume_version_id=rv.id, job_description_id=job.id,
                       quality_score=q_score, quality_breakdown={"components": q_parts, "max": 100},
                       fit_score=f_score if f_score is not None else 0.0, fit_breakdown=f_parts, requirement_evidence=evidence,
                       transferable_skills=scoring.transferable(evidence, ex), suggestions=scoring.suggestions(q_parts, evidence),
                       experience_alignment=scoring.experience_alignment(job.requirements, ex), scoring_version=scoring.SCORING_VERSION)
    db.add(a)
    audit(db, action="analysis.created", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="analysis", entity_id=a.id,
          details={"quality": q_score, "fit": f_score})
    db.commit()
    return a


@router.get("/transitions/{transition_id}/analysis", response_model=AnalysisOut | None)
def get_analysis(transition_id: str, db: DB, ctx: CtxDep):
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    return scoring.latest_analysis(db, t.id)


@router.get("/transitions/{transition_id}/gaps")
def get_gaps(transition_id: str, db: DB, ctx: CtxDep) -> dict:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    return scoring.skill_gaps(db, t)


@router.get("/transitions/{transition_id}/readiness")
def get_readiness(transition_id: str, db: DB, ctx: CtxDep) -> dict:
    t = get_owned(db, CareerTransition, transition_id, ctx.workspace_id, "Career goal")
    return scoring.readiness(db, t)
