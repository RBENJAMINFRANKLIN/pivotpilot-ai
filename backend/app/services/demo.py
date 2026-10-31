"""Seeded demonstration workspace (fictional data, clearly labelled as demo in the UI).
Built through the same services the real journey uses, so every number is genuine output."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssessmentAttempt, AssessmentBlueprint, AssessmentQuestion, CareerTransition, PlanTask, ResumeVersion
from app.seed.demo_content import DEMO_JOB, DEMO_RESUME
from app.services import assessment as engine
from app.services import jobs as jobs_svc
from app.services import planning, scoring
from app.services import resume as resume_svc
from app.services.evidence import record_resume_evidence
from app.services.workspaces import create_guest_workspace

STRONG = {"excel", "statistics", "data-visualization"}  # the fictional teacher answers these correctly


def create_demo_workspace(db: Session):
    ws, token = create_guest_workspace(db)
    ws.is_demo = True
    t = CareerTransition(workspace_id=ws.id, title="Teacher to Data Analyst (demo)", current_role="Mathematics Teacher",
                         current_industry="Education", employment_status="employed", target_role="Junior Data Analyst",
                         deadline=date.today() + timedelta(weeks=26), weekly_hours=6, study_days_per_week=5, budget_amount=0,
                         budget_currency="USD", learning_formats=["interactive", "video"], is_active=True)
    db.add(t)
    text = resume_svc.clean_text(DEMO_RESUME)
    ex, _ = resume_svc.extract(db, workspace_id=ws.id, is_guest=True, text=text)
    rv = ResumeVersion(workspace_id=ws.id, version_number=1, source="paste", sha256="demo", text_content=text,
                       extracted=ex.model_dump(), extraction_method="rules")
    db.add(rv)
    db.flush()
    record_resume_evidence(db, ws.id, rv)
    from app.models import JobDescription, JobRequirement, ResumeAnalysis

    cmap = jobs_svc.analyze_rules(DEMO_JOB)
    job = JobDescription(workspace_id=ws.id, transition_id=t.id, source_type="paste", title="Junior Data Analyst", company="Acme Retail (fictional)",
                         raw_text=DEMO_JOB, analysis_method="rules", prompt_version=jobs_svc.PROMPT_VERSION)
    for i, r in enumerate(cmap.requirements):
        job.requirements.append(JobRequirement(workspace_id=ws.id, position=i, **r.model_dump()))
    db.add(job)
    db.flush()
    q_score, q_parts = scoring.resume_quality(rv.extracted)
    ev = scoring.requirement_evidence(job.requirements, rv.extracted)
    f_score, f_parts = scoring.fit_score(ev)
    db.add(ResumeAnalysis(workspace_id=ws.id, transition_id=t.id, resume_version_id=rv.id, job_description_id=job.id, quality_score=q_score,
                          quality_breakdown={"components": q_parts, "max": 100}, fit_score=f_score or 0, fit_breakdown=f_parts,
                          requirement_evidence=ev, transferable_skills=scoring.transferable(ev, rv.extracted),
                          suggestions=scoring.suggestions(q_parts, ev), experience_alignment=scoring.experience_alignment(job.requirements, rv.extracted),
                          scoring_version=scoring.SCORING_VERSION))
    db.flush()
    bp: AssessmentBlueprint = engine.build_blueprint(db, t, is_guest=True, kind="diagnostic")
    attempt = AssessmentAttempt(workspace_id=ws.id, transition_id=t.id, blueprint_id=bp.id, kind="diagnostic", state={"asked": [], "skills": {}})
    db.add(attempt)
    db.flush()
    while True:
        q = engine.select_next(db, attempt, bp)
        if q is None:
            break
        engine.serve(db, attempt, q)
        db.flush()
        engine.answer(db, attempt, q.id, _demo_answer(q), is_guest=True)
        db.flush()
    engine.finish(db, attempt, bp, force=True)
    db.flush()
    version = planning.build_plan(db, t, reason="Demo plan")
    first = list(db.scalars(select(PlanTask).where(PlanTask.plan_version_id == version.id).order_by(PlanTask.week_number, PlanTask.day_number)))[:3]
    from app.db import utcnow
    from app.models import TaskCompletion

    for x in first:
        x.status, x.completed_at = "completed", utcnow()
        db.add(TaskCompletion(workspace_id=ws.id, task_id=x.id, event="completed", minutes_spent=x.estimated_minutes))
    from app.api.v1.tracking import ApplicationIn, create_application
    from app.deps import Ctx

    ctx = Ctx(workspace=ws, user=None)
    for company, role, cat, status in [("Northwind (fictional)", "Data Analyst", "data analyst", "rejected"),
                                       ("Contoso (fictional)", "Reporting Analyst", "reporting analyst", "screening"),
                                       ("Fabrikam (fictional)", "Junior Data Analyst", "data analyst", "applied")]:
        create_application(db, ctx, ApplicationIn(company=company, role_title=role, role_category=cat, status=status))
    db.commit()
    return ws, token


def _demo_answer(q: AssessmentQuestion):
    a = q.correct_answer
    good = q.skill_id in STRONG
    if isinstance(a, dict):
        return a["accepted"][0] if good else "not sure"
    if isinstance(a, list):
        return a if good else [i for i in range(len(q.choices)) if i not in a][:1]
    return a if good else (a + 1) % len(q.choices)
