"""Learning-plan generation (planner-v1). Deterministic scheduling:

* Skills with a gap are ordered prerequisite-first, then mandatory before preferred,
  then by gap size.
* Hours per skill = taxonomy effort x (gap / 70), minus hours already completed.
* Each skill becomes lessons (60%), exercises (30%) and a checkpoint quiz (10%), chunked
  to fit a study day, plus a milestone when its checkpoint is passed.
* Weekly revision (10%, from week 2) and portfolio-project milestones are included.
* Hard invariant: scheduled minutes in every week <= the user's weekly study minutes.
* If the work does not fit before the deadline, the conflict is reported with feasible
  alternatives (later deadline, more hours, or mandatory-only scope).
* Plans generated before a completed diagnostic are labelled provisional.
* A new version carries completed tasks forward unchanged.
"""

import math
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import api_error
from app.models import (
    AssessmentAttempt,
    CareerTransition,
    LearningPlan,
    LearningPlanVersion,
    LearningResource,
    PlanTask,
    ResourceRecommendation,
)
from app.services import resources as res_svc
from app.services.projects import ensure_projects
from app.services.scoring import skill_gaps
from app.services.taxonomy import SKILL_BY_ID, skill_name

PLANNER_VERSION = "planner-v1"
MAX_CHUNK = 90
CHECKPOINT_MIN = 20
MILESTONE_MIN = 5
REVISION_SHARE = 0.10
PROJECT_MILESTONE_MIN = 120


def _order(items: list[dict]) -> list[dict]:
    by_id = {i["skill_id"]: i for i in items}
    done: list[str] = []
    seen: set[str] = set()

    def visit(sid: str, stack: tuple = ()):
        if sid in seen or sid in stack:
            return
        for p in by_id[sid].get("prerequisites", []):
            if p in by_id:
                visit(p, stack + (sid,))
        seen.add(sid)
        done.append(sid)

    for i in sorted(items, key=lambda i: (i["importance"] != "mandatory", -i["gap"], i["skill_id"])):
        visit(i["skill_id"])
    return [by_id[s] for s in done]


def _chunks(total: int, size: int) -> list[int]:
    if total <= 0:
        return []
    n = math.ceil(total / size)
    base = total // n
    return [base + (1 if i < total - base * n else 0) for i in range(n)]


def completed_minutes_by_skill(db: Session, plan: LearningPlan | None) -> dict[str, int]:
    if not plan or not plan.current_version_id:
        return {}
    rows = db.execute(select(PlanTask.skill_id, func.sum(PlanTask.estimated_minutes)).where(
        PlanTask.plan_version_id == plan.current_version_id, PlanTask.status == "completed",
        PlanTask.task_type.in_(["lesson", "exercise"])).group_by(PlanTask.skill_id)).all()
    return {sid: int(m or 0) for sid, m in rows if sid}


def build_plan(db: Session, t: CareerTransition, *, scope: str = "full", reason: str = "Generated", start: date | None = None) -> LearningPlanVersion:
    gaps = skill_gaps(db, t)
    if gaps["status"] == "no_job":
        raise api_error(409, "NO_JOB", "Add a target job first.")
    diag = db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.transition_id == t.id, AssessmentAttempt.kind == "diagnostic",
                                                     AssessmentAttempt.status == "completed").order_by(AssessmentAttempt.completed_at.desc()))
    status = "final" if diag else "provisional"
    plan = db.scalar(select(LearningPlan).where(LearningPlan.transition_id == t.id))
    done_min = completed_minutes_by_skill(db, plan)

    gap_items = [g for g in gaps["items"] if g["gap"] > 0 and SKILL_BY_ID[g["skill_id"]]["category"] != "professional"]
    if scope == "mandatory_only":
        gap_items = [g for g in gap_items if g["importance"] == "mandatory"]
    ordered = _order(gap_items)
    recs = res_svc.recommend(db, t, gap_items)
    top_res: dict[str, ResourceRecommendation] = {}
    for r in sorted(recs, key=lambda r: r.rank):
        top_res.setdefault(r.skill_id, r)

    weekly_min = int(t.weekly_hours * 60)
    days = t.study_days_per_week
    day_cap = max(15, weekly_min // days)
    chunk = min(MAX_CHUNK, day_cap)
    start = start or (date.today() + timedelta(days=1))

    # 1. Build the ordered task queue.
    queue: list[dict] = []
    skill_plan = []
    for g in ordered:
        sid = g["skill_id"]
        hours = SKILL_BY_ID[sid]["hours"] * (g["gap"] / 70)
        minutes = max(60, int(round(hours * 60)) - int(done_min.get(sid, 0) * 0.8))
        minutes = int(math.ceil(minutes / 15) * 15)
        lesson, exercise = int(minutes * 0.6), int(minutes * 0.3)
        rec = top_res.get(sid)
        resource = db.get(LearningResource, rec.resource_id) if rec else None
        why = (f"{skill_name(sid)} is {g['importance']} for this role"
               + (f" (job: \"{g['job_excerpt'][:100]}\")" if g.get("job_excerpt") else "")
               + f". Your {g['basis']} level is {g['current']:.0f}/100 against a target of {g['target']:.0f}.")
        for i, m in enumerate(_chunks(lesson, chunk), start=1):
            queue.append(dict(skill_id=sid, task_type="lesson", minutes=m, resource_id=resource.id if resource else None,
                              title=f"{skill_name(sid)}: study session {i}" + (f" - {resource.title}" if resource else ""),
                              description=(f"Work through the next part of \"{resource.title}\" ({resource.provider})." if resource
                                           else f"Study {skill_name(sid)} fundamentals using any resource from your list."),
                              criteria="Finish the session and note one thing you learned.",
                              rationale=why + (f" Resource chosen because: {rec.rationale}" if rec else "")))
        for i, m in enumerate(_chunks(exercise, chunk), start=1):
            queue.append(dict(skill_id=sid, task_type="exercise", minutes=m, resource_id=None,
                              title=f"{skill_name(sid)}: practice {i}",
                              description=f"Hands-on exercises applying {skill_name(sid)} (the practice sections of your resource, or a small problem of your own).",
                              criteria="Complete the exercises without looking at solutions first.", rationale=why))
        queue.append(dict(skill_id=sid, task_type="quiz", minutes=min(CHECKPOINT_MIN, day_cap), resource_id=None,
                          title=f"{skill_name(sid)} checkpoint quiz",
                          description=f"Take the {skill_name(sid)} topic check. Course completion alone does not update your assessed level; this quiz does.",
                          criteria=f"Score at least {g['target']:.0f}/100 on the topic check.", rationale=why))
        queue.append(dict(skill_id=sid, task_type="milestone", minutes=MILESTONE_MIN, resource_id=None,
                          title=f"Milestone: {skill_name(sid)} at target level",
                          description="Review your checkpoint result. If below target, the plan will add practice when revised.",
                          criteria=f"Assessed {skill_name(sid)} proficiency of {g['target']:.0f}+ with at least low confidence.", rationale=why))
        skill_plan.append({"skill_id": sid, "name": skill_name(sid), "importance": g["importance"], "initial": g["current"],
                           "basis": g["basis"], "target": g["target"], "gap": g["gap"], "minutes": lesson + exercise + CHECKPOINT_MIN + MILESTONE_MIN,
                           "resource": resource.title if resource else None})

    projects = ensure_projects(db, t, [g["skill_id"] for g in ordered]) if ordered else []
    project_tasks = []
    for p in projects[:1]:  # one portfolio project in the active plan; more are suggested on the Projects page
        for i, ms in enumerate(p.milestones, start=1):
            project_tasks.append(dict(skill_id=None, task_type="project", minutes=min(PROJECT_MILESTONE_MIN, day_cap), resource_id=None,
                                      project_id=p.id, title=f"Project \"{p.title}\" - milestone {i}: {ms['title']}",
                                      description=ms["title"], criteria="Save your work and tick off the milestone.",
                                      rationale=p.rationale))
    # Projects start once roughly half of the skill work is behind you.
    mid = len(queue) // 2
    queue = queue[:mid] + project_tasks + queue[mid:]

    # 2. Schedule into weeks and days without exceeding capacity.
    tasks: list[dict] = []
    weeks: list[dict] = []
    week = 0
    while queue:
        week += 1
        if week > 260:
            break
        used = 0
        day_used = [0] * days
        week_tasks = []
        if week > 1 and tasks:
            rev = max(15, int(weekly_min * REVISION_SHARE))
            prev_skills = sorted({x["skill_id"] for x in tasks if x["week"] == week - 1 and x["skill_id"]})
            if prev_skills:
                week_tasks.append(dict(skill_id=None, task_type="revision", minutes=min(rev, day_cap), resource_id=None,
                                       title="Weekly revision", day=1,
                                       description=f"Review notes and redo one exercise from last week ({', '.join(skill_name(s) for s in prev_skills)}).",
                                       criteria="Summarise last week in three bullet points.",
                                       rationale="Spaced revision improves retention."))
                day_used[0] += min(rev, day_cap)
                used += min(rev, day_cap)
        while queue:
            nxt = queue[0]
            day = next((d for d in range(days) if day_used[d] + nxt["minutes"] <= day_cap), None)
            if day is None or used + nxt["minutes"] > weekly_min:
                break
            queue.pop(0)
            day_used[day] += nxt["minutes"]
            used += nxt["minutes"]
            week_tasks.append({**nxt, "day": day + 1})
        if not week_tasks or (len(week_tasks) == 1 and week_tasks[0]["task_type"] == "revision" and queue and
                              queue[0]["minutes"] > day_cap):
            raise api_error(422, "TASK_TOO_LARGE", "Your study days are too short for the tasks. Increase weekly hours or reduce study days.")
        for x in week_tasks:
            x["week"] = week
        tasks.extend(week_tasks)
        skills_this_week = sorted({x["skill_id"] for x in week_tasks if x["skill_id"]})
        objectives = [f"{skill_name(s)}: " + ", ".join(sorted({x['task_type'] for x in week_tasks if x['skill_id'] == s})) for s in skills_this_week]
        if any(x["task_type"] == "project" for x in week_tasks):
            objectives.append("Portfolio project milestones")
        weeks.append({"week": week, "start_date": (start + timedelta(weeks=week - 1)).isoformat(), "planned_minutes": used,
                      "capacity_minutes": weekly_min, "objectives": objectives or ["Revision"], "skills": skills_this_week})

    total_min = sum(x["minutes"] for x in tasks)
    weeks_needed = len(weeks)
    feasibility: dict = {"weekly_capacity_minutes": weekly_min, "total_minutes": total_min, "weeks_needed": weeks_needed,
                         "end_date": (start + timedelta(weeks=weeks_needed) - timedelta(days=1)).isoformat() if weeks_needed else start.isoformat(),
                         "deadline": t.deadline.isoformat() if t.deadline else None, "conflict": False, "alternatives": []}
    if t.deadline:
        weeks_available = max(0, (t.deadline - start).days // 7)
        feasibility["weeks_available"] = weeks_available
        if weeks_needed > weeks_available:
            feasibility["conflict"] = True
            feasibility["message"] = (f"This plan needs about {weeks_needed} weeks at {t.weekly_hours:g} h/week, but your deadline "
                                      f"leaves {weeks_available}. Choose one of the alternatives.")
            alts = [{"type": "extend_deadline", "deadline": (start + timedelta(weeks=weeks_needed)).isoformat(),
                     "text": f"Move the deadline to {(start + timedelta(weeks=weeks_needed)).isoformat()}."}]
            if weeks_available > 0:
                need_h = math.ceil(total_min / weeks_available / 60 * 1.05)
                if need_h <= 40:
                    alts.append({"type": "increase_hours", "weekly_hours": need_h, "text": f"Study about {need_h} hours per week."})
            if scope == "full" and any(g["importance"] == "preferred" for g in gap_items):
                mand = sum(sp["minutes"] for sp in skill_plan if sp["importance"] == "mandatory")
                alts.append({"type": "reduce_scope", "scope": "mandatory_only",
                             "fits": weeks_available > 0 and mand <= weeks_available * weekly_min * (1 - REVISION_SHARE),
                             "text": "Focus on mandatory skills first and leave preferred skills for later."})
            feasibility["alternatives"] = alts
    # Invariant check (defensive): never exceed weekly capacity.
    for w in weeks:
        assert w["planned_minutes"] <= weekly_min, "planner exceeded weekly capacity"

    if plan is None:
        plan = LearningPlan(workspace_id=t.workspace_id, transition_id=t.id)
        db.add(plan)
        db.flush()
    prev_id = plan.current_version_id
    n = (db.scalar(select(func.max(LearningPlanVersion.version_number)).where(LearningPlanVersion.plan_id == plan.id)) or 0) + 1
    version = LearningPlanVersion(
        workspace_id=t.workspace_id, plan_id=plan.id, version_number=n, status=status, reason=reason[:300],
        based_on_attempt_id=diag.id if diag else None, start_date=start, weeks=weeks, feasibility=feasibility,
        generation_method=PLANNER_VERSION,
        summary={"scope": scope, "skills": skill_plan, "total_hours": round(total_min / 60, 1),
                 "target_outcomes": [f"Reach {sp['target']:.0f}/100 in {sp['name']}" for sp in skill_plan],
                 "status_note": ("Provisional: based on your resume and self-ratings. Complete the assessment for a final plan."
                                 if status == "provisional" else "Based on your assessment results."),
                 "professional_skills": [{"skill_id": g["skill_id"], "name": skill_name(g["skill_id"]), "how": "Practised through mock interviews and projects"}
                                         for g in gaps["items"] if g["gap"] > 0 and SKILL_BY_ID[g["skill_id"]]["category"] == "professional"]})
    db.add(version)
    db.flush()
    if prev_id:  # preserve completed work
        for old in db.scalars(select(PlanTask).where(PlanTask.plan_version_id == prev_id, PlanTask.status == "completed")):
            db.add(PlanTask(workspace_id=t.workspace_id, plan_version_id=version.id, week_number=0, day_number=0,
                            scheduled_date=old.scheduled_date, skill_id=old.skill_id, task_type=old.task_type, title=old.title,
                            description=old.description, resource_id=old.resource_id, project_id=old.project_id,
                            estimated_minutes=old.estimated_minutes, status="completed", completion_criteria=old.completion_criteria,
                            rationale=old.rationale, carried_from_task_id=old.carried_from_task_id or old.id, completed_at=old.completed_at))
    for x in tasks:
        db.add(PlanTask(workspace_id=t.workspace_id, plan_version_id=version.id, week_number=x["week"], day_number=x["day"],
                        scheduled_date=start + timedelta(weeks=x["week"] - 1, days=x["day"] - 1), skill_id=x["skill_id"],
                        task_type=x["task_type"], title=x["title"][:300], description=x["description"], resource_id=x["resource_id"],
                        project_id=x.get("project_id"), estimated_minutes=x["minutes"], completion_criteria=x["criteria"],
                        rationale=x["rationale"]))
    plan.current_version_id = version.id
    plan.status = "active"
    db.flush()
    return version


def maybe_revise(db: Session, t: CareerTransition, attempt: AssessmentAttempt) -> dict | None:
    """After an assessment, revise the remaining plan when the evidence justifies it."""
    plan = db.scalar(select(LearningPlan).where(LearningPlan.transition_id == t.id))
    if not plan or not plan.current_version_id:
        return None
    current = db.get(LearningPlanVersion, plan.current_version_id)
    reasons = []
    if attempt.kind == "diagnostic" and current.status == "provisional":  # type: ignore[union-attr]
        reasons.append("diagnostic results are now available")
    planned = {s["skill_id"]: s for s in current.summary.get("skills", [])}  # type: ignore[union-attr]
    pending = {sid for (sid,) in db.execute(select(PlanTask.skill_id).where(
        PlanTask.plan_version_id == current.id, PlanTask.status != "completed", PlanTask.skill_id.is_not(None)))}  # type: ignore[union-attr]
    for sid, r in (attempt.results or {}).get("skills", {}).items():
        if r["score"] is None or sid not in planned:
            continue
        if r["score"] >= planned[sid]["target"] and sid in pending:
            reasons.append(f"{r['name']} reached its target ({r['score']:.0f})")
        elif r["score"] <= planned[sid]["initial"] - 15:
            reasons.append(f"{r['name']} scored lower than expected ({r['score']:.0f})")
    if not reasons:
        return None
    v = build_plan(db, t, scope=current.summary.get("scope", "full"), reason="Revised: " + "; ".join(reasons))  # type: ignore[union-attr]
    return {"version": v.version_number, "reasons": reasons}

