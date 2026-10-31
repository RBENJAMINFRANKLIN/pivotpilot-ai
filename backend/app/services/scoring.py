"""Deterministic, versioned scoring (scoring-v1). Every score returns its components,
weights and the reasons behind each component so the UI can explain it.

Separate indicators are never folded into each other:
  resume quality   - how well the document is written (independent of the target job)
  role fit         - how much resume *evidence* exists for each job requirement
  assessed skill   - quiz / practical results only
  experience       - stated years vs required years
  projects         - rubric-assessed portfolio work
  interview        - mock-interview rubric scores
Keyword presence is treated as a claim with supporting text, never as proof of competence.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CareerTransition,
    Interview,
    JobDescription,
    JobRequirement,
    Project,
    ProjectEvidence,
    ResumeAnalysis,
)
from app.services.evidence import claimed_scores, estimate, latest_assessed
from app.services.taxonomy import SKILL_BY_ID, related, skill_name

SCORING_VERSION = "scoring-v1"
IMPORTANCE_WEIGHT = {"mandatory": 3.0, "preferred": 1.0}
EVIDENCE_STRENGTH = {"demonstrated": 1.0, "listed": 0.6, "transferable": 0.3, "missing": 0.0}
TARGET_PROFICIENCY = {"mandatory": 70.0, "preferred": 60.0}
READINESS_WEIGHTS = {
    "resume_quality": 0.10, "role_fit": 0.10, "assessed_proficiency": 0.30,
    "experience_alignment": 0.15, "project_evidence": 0.20, "interview_performance": 0.15,
}
SKILL_CATEGORIES = {"skill", "tool", "domain", "professional"}


def resume_quality(ex: dict) -> tuple[float, list[dict]]:
    sections = set(ex.get("sections", []))
    contact = ex.get("contact", {})
    bullets = max(ex.get("bullet_count", 0), 1)
    words = ex.get("word_count", 0)
    exps = ex.get("experiences", [])
    comps = []

    pts = (10 if "experience" in sections else 0) + (5 if "education" in sections else 0) + (5 if "skills" in sections else 0) + (5 if "summary" in sections else 0)
    missing = [s for s in ("experience", "education", "skills", "summary") if s not in sections]
    comps.append(dict(id="structure", label="Clear sections", points=pts, max=25,
                      detail=f"Found: {', '.join(sorted(sections)) or 'no recognised headings'}.",
                      suggestion=f"Add clear headings for: {', '.join(missing)}." if missing else None))
    pts = (5 if contact.get("email") else 0) + (5 if contact.get("phone") or contact.get("link") else 0)
    comps.append(dict(id="contact", label="Contact details present", points=pts, max=10,
                      detail="Checks only that an email and a phone number or profile link are present.",
                      suggestion=None if pts == 10 else "Include an email address and a phone number or LinkedIn/portfolio link."))
    ratio = ex.get("quantified_bullets", 0) / bullets
    pts = round(min(1.0, ratio / 0.4) * 20, 1)
    comps.append(dict(id="quantified", label="Quantified achievements", points=pts, max=20,
                      detail=f"{ex.get('quantified_bullets', 0)} of {ex.get('bullet_count', 0)} bullet points include a number.",
                      suggestion=None if pts >= 18 else "Where true, add numbers to achievements (how many, how much, how often, % change)."))
    ratio = ex.get("action_verb_bullets", 0) / bullets
    pts = round(min(1.0, ratio / 0.6) * 15, 1)
    comps.append(dict(id="action_verbs", label="Bullets start with action verbs", points=pts, max=15,
                      detail=f"{ex.get('action_verb_bullets', 0)} of {ex.get('bullet_count', 0)} bullet points start with an action verb.",
                      suggestion=None if pts >= 13 else "Start bullet points with what you did (e.g. 'Built', 'Led', 'Analysed')."))
    if 350 <= words <= 900:
        pts, note = 15, None
    elif 200 <= words < 350 or 900 < words <= 1300:
        pts, note = 8, "Aim for roughly 350-900 words (about one to two pages)."
    else:
        pts, note = 3, "The resume is very short or very long; aim for roughly 350-900 words."
    comps.append(dict(id="length", label="Appropriate length", points=pts, max=15, detail=f"{words} words.", suggestion=note))
    dated = sum(1 for e in exps if e.get("start"))
    pts = round((dated / len(exps)) * 15, 1) if exps else 0
    comps.append(dict(id="timeline", label="Dated work history", points=pts, max=15,
                      detail=f"{dated} of {len(exps)} roles have dates." if exps else "No dated roles were recognised.",
                      suggestion=None if pts >= 13 else "Show start and end dates (month and year) for each role."))
    return round(sum(c["points"] for c in comps), 1), comps


CONTEXT_ORDER = {"experience": 0, "projects": 1, "summary": 2, "skills_list": 3}


def _resume_skill_index(ex: dict) -> dict[str, list[dict]]:
    """Skill -> evidence, strongest context (work history) first."""
    return {s["skill_id"]: sorted(s["evidence"], key=lambda e: CONTEXT_ORDER.get(e["context"], 4)) for s in ex.get("skills", [])}


def requirement_evidence(reqs: list[JobRequirement], ex: dict) -> list[dict]:
    index = _resume_skill_index(ex)
    out = []
    for r in reqs:
        item = dict(requirement_id=r.id, label=r.label, category=r.category, importance=r.importance, skill_id=r.skill_id,
                    job_excerpt=r.source_excerpt, job_source_url=r.source_url, confidence=r.confidence,
                    resume_excerpts=[], status="n/a", strength=None, note=None)
        if r.category in SKILL_CATEGORIES and r.skill_id:
            ev = index.get(r.skill_id, [])
            if any(e["context"] in ("experience", "projects", "summary") for e in ev):
                item.update(status="demonstrated", resume_excerpts=[e["excerpt"] for e in ev][:3],
                            note="Mentioned in your work history. This is resume evidence, not a measure of skill.")
            elif ev:
                item.update(status="listed", resume_excerpts=[e["excerpt"] for e in ev][:3],
                            note="Listed on your resume without an example of using it.")
            else:
                rel = [s for s in related(r.skill_id) if s in index]
                if rel:
                    item.update(status="transferable", resume_excerpts=[index[rel[0]][0]["excerpt"]],
                                note=f"Not mentioned, but related experience with {skill_name(rel[0])} may transfer.")
                else:
                    item.update(status="missing", note="No evidence found on your resume.")
            item["strength"] = EVIDENCE_STRENGTH[item["status"]]
        elif r.category in SKILL_CATEGORIES:
            item.update(status="unknown", note="This requirement is not in our skill catalogue, so it is not scored. Review it yourself.")
        elif r.category == "education":
            edu = " ".join(ex.get("education", [])).lower()
            met = any(w in edu for w in ("bachelor", "master", "degree", "phd", "b.a", "b.sc", "ba ", "bsc", "msc", "m.a", "ma "))
            item.update(status="met" if met else "unknown", resume_excerpts=ex.get("education", [])[:2],
                        note=None if met else "We could not confirm a matching qualification; check this yourself.")
        out.append(item)
    return out


def fit_score(evidence: list[dict]) -> tuple[float | None, dict]:
    scored = [e for e in evidence if e["strength"] is not None]
    if not scored:
        return None, {"reason": "No scoreable skill requirements were found."}
    total = sum(IMPORTANCE_WEIGHT[e["importance"]] for e in scored)
    got = sum(IMPORTANCE_WEIGHT[e["importance"]] * e["strength"] for e in scored)
    by_imp = {}
    for imp in ("mandatory", "preferred"):
        items = [e for e in scored if e["importance"] == imp]
        by_imp[imp] = {"count": len(items), "with_evidence": sum(1 for e in items if e["status"] in ("demonstrated", "listed"))}
    return round(100 * got / total, 1), {
        "method": "Weighted share of job requirements with supporting resume evidence",
        "weights": {"importance": IMPORTANCE_WEIGHT, "evidence_strength": EVIDENCE_STRENGTH},
        "coverage": by_imp,
        "caveat": "Role fit measures resume evidence only. It is not a hiring probability and not a measure of skill.",
    }


def experience_alignment(reqs: list[JobRequirement], ex: dict) -> dict:
    need = next((r for r in reqs if r.category == "experience" and r.min_years), None)
    have = ex.get("total_years_experience")
    if not need:
        return {"score": None, "status": "not_stated", "required_years": None, "resume_years": have,
                "note": "The job does not state a years-of-experience requirement."}
    if have is None:
        return {"score": None, "status": "unknown", "required_years": need.min_years, "resume_years": None,
                "note": "We could not read dates from your resume, so total experience is unknown.", "job_excerpt": need.source_excerpt}
    score = round(min(1.0, have / need.min_years) * 100, 1)  # type: ignore[operator]
    return {"score": score, "status": "met" if have >= need.min_years else "below", "required_years": need.min_years,  # type: ignore[operator]
            "resume_years": have, "job_excerpt": need.source_excerpt,
            "note": "Total dated work experience compared with the stated requirement. Relevance of that experience is shown in the requirement list."}


def transferable(evidence: list[dict], ex: dict) -> list[dict]:
    out = []
    for e in evidence:
        if e["status"] == "transferable":
            out.append({"skill_id": e["skill_id"], "label": e["label"], "excerpt": e["resume_excerpts"][0], "reason": e["note"]})
        elif e["status"] == "demonstrated" and e["category"] == "professional":
            out.append({"skill_id": e["skill_id"], "label": e["label"], "excerpt": e["resume_excerpts"][0],
                        "reason": "A professional competency the job asks for, shown in your current work."})
    return out


def suggestions(quality: list[dict], evidence: list[dict]) -> list[dict]:
    out = [{"type": "writing", "text": c["suggestion"]} for c in quality if c.get("suggestion")]
    listed = [e["label"] for e in evidence if e["status"] == "listed" and e["importance"] == "mandatory"]
    if listed:
        out.append({"type": "evidence", "text": f"If you have used {', '.join(listed[:4])} in practice, add a bullet point describing what you did and the result."})
    missing = [e["label"] for e in evidence if e["status"] in ("missing", "transferable") and e["importance"] == "mandatory"]
    if missing:
        out.append({"type": "gap", "text": f"No evidence yet for: {', '.join(missing[:5])}. Only add these once you have real experience, for example from the portfolio projects in your plan."})
    return out


def latest_analysis(db: Session, transition_id: str) -> ResumeAnalysis | None:
    return db.scalar(select(ResumeAnalysis).where(ResumeAnalysis.transition_id == transition_id).order_by(ResumeAnalysis.created_at.desc()))


def current_job(db: Session, transition_id: str) -> JobDescription | None:
    return db.scalar(select(JobDescription).where(JobDescription.transition_id == transition_id).order_by(JobDescription.created_at.desc()))


def skill_gaps(db: Session, t: CareerTransition) -> dict:
    job = current_job(db, t.id)
    if not job:
        return {"status": "no_job", "items": []}
    assessed = latest_assessed(db, t.workspace_id)
    claimed = claimed_scores(db, t.workspace_id)
    items, any_provisional = [], False
    seen = set()
    for r in job.requirements:
        if r.category not in SKILL_CATEGORIES or not r.skill_id or r.skill_id in seen:
            continue
        seen.add(r.skill_id)
        est = estimate(r.skill_id, assessed, claimed)
        target = TARGET_PROFICIENCY[r.importance]
        gap = max(0.0, round(target - est["score"], 1))
        any_provisional |= est["basis"] == "provisional"
        a = assessed.get(r.skill_id)
        items.append(dict(skill_id=r.skill_id, name=skill_name(r.skill_id), category=SKILL_BY_ID[r.skill_id]["category"],
                          importance=r.importance, job_excerpt=r.source_excerpt, requirement_id=r.id,
                          current=est["score"], basis=est["basis"], confidence=est["confidence"], level=est["level"],
                          target=target, gap=gap, claimed=claimed.get(r.skill_id, {}),
                          assessed_status=(a.confidence if a else "not_assessed"),
                          prerequisites=r.prerequisite_skill_ids))
    items.sort(key=lambda i: (-IMPORTANCE_WEIGHT[i["importance"]] * i["gap"], i["name"]))
    return {"status": "provisional" if any_provisional else "assessed", "items": items,
            "note": "Gaps marked provisional are based on your resume and self-ratings until you complete the assessment."}


def readiness(db: Session, t: CareerTransition) -> dict:
    comps: dict[str, dict] = {}
    a = latest_analysis(db, t.id)
    if a:
        comps["resume_quality"] = {"score": a.quality_score}
        if a.fit_score is not None:
            comps["role_fit"] = {"score": a.fit_score}
        if a.experience_alignment.get("score") is not None:
            comps["experience_alignment"] = {"score": a.experience_alignment["score"]}
    gaps = skill_gaps(db, t)
    assessed_items = [i for i in gaps["items"] if i["basis"] == "assessed"]
    if assessed_items:
        w = sum(IMPORTANCE_WEIGHT[i["importance"]] for i in assessed_items)
        s = sum(IMPORTANCE_WEIGHT[i["importance"]] * min(1.0, i["current"] / i["target"]) for i in assessed_items)
        comps["assessed_proficiency"] = {"score": round(100 * s / w, 1),
                                         "coverage": f"{len(assessed_items)} of {len(gaps['items'])} required skills assessed"}
    proj_scores = [p.score for p in db.scalars(select(ProjectEvidence).join(Project, Project.id == ProjectEvidence.project_id)
                   .where(Project.transition_id == t.id, ProjectEvidence.score.is_not(None)))]
    if proj_scores:
        comps["project_evidence"] = {"score": round(sum(proj_scores) / len(proj_scores), 1), "count": len(proj_scores)}
    iv = [i.overall_score for i in db.scalars(select(Interview).where(Interview.transition_id == t.id, Interview.status == "completed")
          .order_by(Interview.completed_at.desc()).limit(3)) if i.overall_score is not None]
    if iv:
        comps["interview_performance"] = {"score": round(sum(iv) / len(iv), 1), "count": len(iv)}
    available = {k: v for k, v in comps.items() if k in READINESS_WEIGHTS}
    missing = [k for k in READINESS_WEIGHTS if k not in available]
    overall = None
    if available:
        wsum = sum(READINESS_WEIGHTS[k] for k in available)
        overall = round(sum(READINESS_WEIGHTS[k] * v["score"] for k, v in available.items()) / wsum, 1)
    return {"scoring_version": SCORING_VERSION, "overall": overall, "components": comps, "weights": READINESS_WEIGHTS,
            "missing_components": missing, "provisional": "assessed_proficiency" not in available,
            "caveat": "Readiness summarises your preparation evidence. It is not a prediction of being hired."}
