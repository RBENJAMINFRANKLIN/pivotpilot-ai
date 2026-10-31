"""Portfolio project suggestions matched to skill gaps, plus rubric-based evidence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CareerTransition, Project
from app.seed.projects import PROJECTS, STANDARD_RUBRIC
from app.seed.skills import role_family
from app.services.taxonomy import skill_name


def suggest(target_role: str, gap_skills: list[str], limit: int = 3) -> list[tuple[dict, list[str]]]:
    family = role_family(target_role)
    scored = []
    for tpl in PROJECTS:
        overlap = [s for s in tpl["skills"] if s in gap_skills]
        if not overlap:
            continue
        # Earlier (higher-priority) gaps count more; same-family templates get a bonus.
        weight = sum(len(gap_skills) - gap_skills.index(s) for s in overlap) + (5 if tpl["family"] == family else 0)
        scored.append((weight, tpl, overlap))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [(tpl, overlap) for _, tpl, overlap in scored[:limit]]


def ensure_projects(db: Session, t: CareerTransition, gap_skills: list[str]) -> list[Project]:
    existing = {p.template_id: p for p in db.scalars(select(Project).where(Project.transition_id == t.id))}
    out = []
    for tpl, overlap in suggest(t.target_role, gap_skills):
        p = existing.get(tpl["id"])
        if p is None:
            p = Project(workspace_id=t.workspace_id, transition_id=t.id, template_id=tpl["id"], title=tpl["title"],
                        problem_statement=tpl["problem"], required_skills=tpl["skills"],
                        milestones=[{"title": m, "done": False} for m in tpl["milestones"]], deliverables=tpl["deliverables"],
                        rubric=STANDARD_RUBRIC, resume_evidence=tpl["evidence"],
                        rationale=f"Builds practical evidence for {', '.join(skill_name(s) for s in overlap)}, which your target job asks for.")
            db.add(p)
        out.append(p)
    # Keep projects the user already started, even if they no longer rank highly.
    out += [p for p in existing.values() if p not in out and p.status in ("in_progress", "completed")]
    db.flush()
    return out


def rubric_score(scores: dict[str, int]) -> float:
    """Self-assessment on the 1-4 rubric scale -> 0..100. Recorded as project evidence only;
    it never changes assessed (quiz) proficiency."""
    ids = [c["id"] for c in STANDARD_RUBRIC]
    vals = [max(1, min(4, int(scores.get(i, 1)))) for i in ids]
    return round(sum((v - 1) / 3 for v in vals) / len(vals) * 100, 1)
