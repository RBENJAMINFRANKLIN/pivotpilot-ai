"""Idempotent loading of reference data (skills, questions, resources). Safe to run on
every deploy: existing rows are updated in place, nothing user-owned is touched."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AssessmentQuestion, LearningResource, Skill, SkillAlias, SkillPrerequisite
from app.seed.questions import QUESTIONS
from app.seed.resources import RESOURCES
from app.seed.skills import SKILLS


def load_reference_data(db: Session) -> dict[str, int]:
    seen_alias: set[str] = set()
    for sk in SKILLS:
        row = db.get(Skill, sk["id"]) or Skill(id=sk["id"])
        row.name, row.category, row.learn_hours = sk["name"], sk["category"], sk["hours"]
        db.merge(row)
        for a in sk["aliases"]:
            a = a.lower()
            if a in seen_alias:
                raise ValueError(f"duplicate alias {a!r}")
            seen_alias.add(a)
    db.flush()
    db.execute(delete(SkillAlias))
    db.execute(delete(SkillPrerequisite))
    for sk in SKILLS:
        for a in sk["aliases"]:
            db.add(SkillAlias(skill_id=sk["id"], alias=a.lower()))
        for p in sk["prereqs"]:
            db.add(SkillPrerequisite(skill_id=sk["id"], prerequisite_id=p))

    for qd in QUESTIONS:
        row = db.get(AssessmentQuestion, qd["id"]) or AssessmentQuestion(id=qd["id"])
        for k, v in qd.items():
            setattr(row, k, v)
        row.origin, row.validated, row.workspace_id = "curated", True, None
        db.merge(row)

    existing = {r.canonical_url: r for r in db.scalars(select(LearningResource).where(LearningResource.source == "curated"))}
    for rd in RESOURCES:
        row = existing.get(rd["canonical_url"])
        if row is None:
            row = LearningResource(source="curated", verification_status="unverified")
            db.add(row)
        for k, v in rd.items():
            setattr(row, k, v)
    db.commit()
    return {"skills": len(SKILLS), "questions": len(QUESTIONS), "resources": len(RESOURCES)}
