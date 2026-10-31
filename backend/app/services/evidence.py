"""Skill evidence and proficiency.

Evidence types are stored separately and never merged into one number:
  self_reported, resume  -> *claimed* evidence; used only for a provisional estimate
  quiz, practical        -> *assessed* evidence; the only inputs to assessed proficiency
  project                -> practical project evidence (rubric self/AI assessment)
  course_completion      -> recorded, but never raises assessed proficiency on its own
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ProficiencyHistory, ResumeVersion, SkillEvidence

METHOD_VERSION = "proficiency-v1"
BANDS = [(85, "advanced"), (70, "proficient"), (50, "developing"), (25, "beginner"), (0, "novice")]
SELF_LEVEL_SCORE = {1: 5, 2: 25, 3: 45, 4: 60, 5: 75}  # self-report is capped below "advanced"
RESUME_CONTEXT_SCORE = {"experience": 55, "projects": 50, "summary": 45, "skills_list": 40, "education": 35, "other": 35}


def level_for(score: float | None) -> str:
    if score is None:
        return "insufficient_evidence"
    for threshold, name in BANDS:
        if score >= threshold:
            return name
    return "novice"


def record_self_reported(db: Session, workspace_id: str, skills: list[dict]) -> None:
    db.execute(delete(SkillEvidence).where(SkillEvidence.workspace_id == workspace_id, SkillEvidence.evidence_type == "self_reported"))
    for s in skills:
        db.add(SkillEvidence(workspace_id=workspace_id, skill_id=s["skill_id"], evidence_type="self_reported",
                             score=SELF_LEVEL_SCORE.get(int(s["level"]), 5), confidence=0.25,
                             methodology="self-report-1to5", excerpt=f"Self-rated {s['level']}/5"))


def record_resume_evidence(db: Session, workspace_id: str, resume: ResumeVersion) -> None:
    db.execute(delete(SkillEvidence).where(SkillEvidence.workspace_id == workspace_id, SkillEvidence.evidence_type == "resume"))
    for sk in resume.extracted.get("skills", []):
        contexts = [e["context"] for e in sk["evidence"]]
        best = max((RESUME_CONTEXT_SCORE.get(c, 35) for c in contexts), default=35)
        db.add(SkillEvidence(workspace_id=workspace_id, skill_id=sk["skill_id"], evidence_type="resume", source_ref=resume.id,
                             score=best, confidence=0.4 if "experience" in contexts else 0.3,
                             excerpt=sk["evidence"][0]["excerpt"] if sk["evidence"] else None, methodology="resume-mention-context"))


def latest_resume(db: Session, workspace_id: str) -> ResumeVersion | None:
    return db.scalar(select(ResumeVersion).where(ResumeVersion.workspace_id == workspace_id).order_by(ResumeVersion.version_number.desc()))


def latest_assessed(db: Session, workspace_id: str) -> dict[str, ProficiencyHistory]:
    rows = db.scalars(select(ProficiencyHistory).where(ProficiencyHistory.workspace_id == workspace_id)
                      .order_by(ProficiencyHistory.created_at)).all()
    out: dict[str, ProficiencyHistory] = {}
    for r in rows:
        out[r.skill_id] = r  # later rows overwrite earlier ones
    return out


def claimed_scores(db: Session, workspace_id: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for ev in db.scalars(select(SkillEvidence).where(SkillEvidence.workspace_id == workspace_id,
                                                     SkillEvidence.evidence_type.in_(["self_reported", "resume"]))):
        d = out.setdefault(ev.skill_id, {})
        d[ev.evidence_type] = ev.score
    return out


def estimate(skill_id: str, assessed: dict[str, ProficiencyHistory], claimed: dict[str, dict]) -> dict:
    """Best current estimate for planning, with its basis made explicit."""
    a = assessed.get(skill_id)
    if a and a.score is not None and a.confidence != "insufficient":
        return {"score": a.score, "basis": "assessed", "confidence": a.confidence, "level": a.level}
    c = claimed.get(skill_id, {})
    vals = [v for v in (c.get("resume"), c.get("self_reported")) if v is not None]
    if vals:
        score = max(vals)
        return {"score": score, "basis": "provisional", "confidence": "low", "level": level_for(score)}
    return {"score": 5.0, "basis": "provisional", "confidence": "low", "level": "novice"}
