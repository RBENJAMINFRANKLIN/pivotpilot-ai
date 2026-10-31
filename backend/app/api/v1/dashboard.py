from datetime import date, timedelta

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, GUEST_COOKIE, CtxDep, OptionalCtxDep
from app.errors import api_error
from app.models import (
    AssessmentAttempt,
    CareerTransition,
    Interview,
    LearningPlan,
    LearningPlanVersion,
    PlanTask,
    ProficiencyHistory,
    Project,
    TaskCompletion,
)
from app.security.ratelimit import enforce
from app.services import applications as app_svc
from app.services.evidence import latest_resume
from app.services.scoring import latest_analysis, readiness, skill_gaps
from app.services.taxonomy import skill_name

router = APIRouter(tags=["dashboard"])


def next_actions(db, t: CareerTransition | None, ws_id: str) -> list[dict]:
    if t is None:
        return [{"id": "create_goal", "label": "Create your first career goal", "route": "/goals"}]
    acts = []
    if latest_resume(db, ws_id) is None:
        acts.append({"id": "add_resume", "label": "Add your resume or career details", "route": "/intake"})
    analysis = latest_analysis(db, t.id)
    from app.services.scoring import current_job

    if current_job(db, t.id) is None:
        acts.append({"id": "add_job", "label": "Add the job you are aiming for", "route": "/intake"})
    elif analysis is None and latest_resume(db, ws_id):
        acts.append({"id": "run_analysis", "label": "Run your fit analysis", "route": "/analysis"})
    attempts = list(db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.transition_id == t.id)))
    diag_done = any(a.kind == "diagnostic" and a.status == "completed" for a in attempts)
    if analysis and not diag_done:
        in_prog = any(a.kind == "diagnostic" and a.status == "in_progress" for a in attempts)
        acts.append({"id": "take_assessment", "label": "Continue your skills assessment" if in_prog else "Take the skills assessment (about 15 minutes)",
                     "route": "/assessment"})
    plan = db.scalar(select(LearningPlan).where(LearningPlan.transition_id == t.id))
    version = db.get(LearningPlanVersion, plan.current_version_id) if plan and plan.current_version_id else None
    if analysis and (version is None or (version.status == "provisional" and diag_done)):
        acts.append({"id": "generate_plan", "label": "Generate your final learning plan" if diag_done else "Generate a provisional plan",
                     "route": "/plan"})
    if version:
        if version.feasibility.get("conflict"):
            acts.append({"id": "resolve_deadline", "label": "Your deadline is not realistic. Pick an alternative", "route": "/plan"})
        checks = [x for x in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == version.id, PlanTask.task_type == "quiz",
                                                               PlanTask.status != "completed"))]
        for q in checks:
            lessons_left = db.scalar(select(func.count(PlanTask.id)).where(PlanTask.plan_version_id == version.id, PlanTask.skill_id == q.skill_id,
                                                                            PlanTask.task_type == "lesson", PlanTask.status != "completed"))
            if lessons_left == 0:
                acts.append({"id": f"topic_check_{q.skill_id}", "label": f"Take the {skill_name(q.skill_id)} checkpoint quiz", "route": f"/assessment?skill={q.skill_id}"})
                break
        task = db.scalar(select(PlanTask).where(PlanTask.plan_version_id == version.id, PlanTask.status.in_(["pending", "in_progress"]),
                                                PlanTask.week_number > 0).order_by(PlanTask.scheduled_date, PlanTask.day_number))
        if task and plan.status == "active":  # type: ignore[union-attr]
            due = "overdue" if task.scheduled_date < date.today() else "today" if task.scheduled_date == date.today() else task.scheduled_date.isoformat()
            acts.append({"id": "next_task", "label": f"{task.title} ({task.estimated_minutes} min, {due})", "route": "/plan", "task_id": task.id})
        if plan.status == "paused":  # type: ignore[union-attr]
            acts.append({"id": "resume_plan", "label": "Your plan is paused. Resume when you are ready", "route": "/plan"})
    if diag_done and not db.scalar(select(Interview.id).where(Interview.transition_id == t.id)):
        acts.append({"id": "mock_interview", "label": "Practise a mock interview", "route": "/interviews"})
    return acts[:5]


@router.get("/dashboard")
def dashboard(db: DB, ctx: CtxDep) -> dict:
    ws = ctx.workspace_id
    t = db.scalar(select(CareerTransition).where(CareerTransition.workspace_id == ws, CareerTransition.is_active))
    out: dict = {"transition": None, "next_actions": next_actions(db, t, ws), "is_demo": ctx.workspace.is_demo}
    rv = latest_resume(db, ws)
    out["resume"] = {"id": rv.id, "version": rv.version_number, "created_at": rv.created_at.isoformat(), "source": rv.source} if rv else None
    out["applications"] = app_svc.analytics(db, ws)
    if t is None:
        return out
    out["transition"] = {"id": t.id, "title": t.title, "current_role": t.current_role, "target_role": t.target_role,
                         "deadline": t.deadline.isoformat() if t.deadline else None, "weekly_hours": t.weekly_hours}
    a = latest_analysis(db, t.id)
    out["scores"] = {"resume_quality": a.quality_score if a else None, "role_fit": a.fit_score if a else None,
                     "readiness": readiness(db, t)}
    gaps = skill_gaps(db, t)
    out["gaps"] = {"status": gaps["status"], "items": gaps["items"][:8]}
    prof = {}
    for p in db.scalars(select(ProficiencyHistory).where(ProficiencyHistory.workspace_id == ws).order_by(ProficiencyHistory.created_at)):
        prof.setdefault(p.skill_id, []).append({"score": p.score, "confidence": p.confidence, "at": p.created_at.isoformat()})
    out["proficiency"] = [{"skill_id": k, "name": skill_name(k), "latest": v[-1], "history": v} for k, v in prof.items()]
    plan = db.scalar(select(LearningPlan).where(LearningPlan.transition_id == t.id))
    out["plan"] = None
    out["weekly_hours"] = []
    if plan and plan.current_version_id:
        v = db.get(LearningPlanVersion, plan.current_version_id)
        tasks = list(db.scalars(select(PlanTask).where(PlanTask.plan_version_id == v.id)))  # type: ignore[union-attr]
        sched = [x for x in tasks if x.week_number > 0]
        week_now = max(1, (date.today() - v.start_date).days // 7 + 1)  # type: ignore[union-attr]
        this_week = [x for x in sched if x.week_number == week_now]
        out["plan"] = {"version": v.version_number, "status": v.status, "plan_status": plan.status, "weeks": len(v.weeks),  # type: ignore[union-attr]
                       "current_week": week_now, "conflict": v.feasibility.get("conflict"),  # type: ignore[union-attr]
                       "progress_percent": round(100 * sum(x.estimated_minutes for x in sched if x.status == "completed") / max(1, sum(x.estimated_minutes for x in sched)), 1),
                       "this_week": {"planned_minutes": sum(x.estimated_minutes for x in this_week),
                                     "completed_minutes": sum(x.estimated_minutes for x in this_week if x.status == "completed"),
                                     "capacity_minutes": int(t.weekly_hours * 60)},
                       "upcoming_checkpoints": [{"skill_id": x.skill_id, "name": skill_name(x.skill_id), "date": x.scheduled_date.isoformat()}  # type: ignore[arg-type]
                                                for x in sorted(sched, key=lambda x: x.scheduled_date) if x.task_type == "quiz" and x.status != "completed"][:3]}
        since = date.today() - timedelta(weeks=8)
        rows = db.execute(select(TaskCompletion.created_at, PlanTask.estimated_minutes, TaskCompletion.minutes_spent)
                          .join(PlanTask, PlanTask.id == TaskCompletion.task_id)
                          .where(TaskCompletion.workspace_id == ws, TaskCompletion.event == "completed")).all()
        weeks: dict[str, float] = {}
        for created, est, spent in rows:
            d = created.date()
            if d >= since:
                key = (d - timedelta(days=d.weekday())).isoformat()
                weeks[key] = weeks.get(key, 0) + (spent or est) / 60
        out["weekly_hours"] = [{"week": k, "hours": round(v, 1)} for k, v in sorted(weeks.items())]
    out["projects"] = [{"id": p.id, "title": p.title, "status": p.status,
                        "next_milestone": next((m["title"] for m in p.milestones if not m.get("done")), None),
                        "done": sum(1 for m in p.milestones if m.get("done")), "total": len(p.milestones)}
                       for p in db.scalars(select(Project).where(Project.transition_id == t.id)) if p.status != "dropped"][:3]
    out["interviews"] = [{"id": i.id, "status": i.status, "overall_score": i.overall_score, "started_at": i.started_at.isoformat()}
                         for i in db.scalars(select(Interview).where(Interview.transition_id == t.id).order_by(Interview.started_at.desc()).limit(5))]
    return out


@router.post("/demo/start")
def start_demo(request: Request, response: Response, db: DB, ctx: OptionalCtxDep) -> dict:
    """Explicit demonstration mode: a separate, clearly labelled guest workspace with sample data."""
    if not get_settings().demo_mode_enabled:
        raise api_error(404, "NOT_FOUND", "Demo mode is disabled.")
    if ctx and not ctx.is_guest:
        raise api_error(409, "SIGNED_IN", "Sign out to open the demo workspace; your account data is not touched.")
    enforce(request, "guest_create", get_settings().rate_limit_guest_create_per_hour, 3600)
    from app.services.demo import create_demo_workspace

    ws, token = create_demo_workspace(db)
    response.set_cookie(GUEST_COOKIE, token, max_age=get_settings().guest_retention_days * 86400, httponly=True,
                        secure=get_settings().cookie_secure, samesite="lax", path="/")
    return {"ok": True, "workspace_id": ws.id}
