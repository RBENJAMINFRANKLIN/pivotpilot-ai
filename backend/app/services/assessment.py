"""Adaptive diagnostic assessment engine (adaptive-v1).

A bounded, deterministic heuristic, no IRT/statistical model (there is no calibration data):

* Blueprint: required skills from the target job's competency map, weighted by importance,
  with a minimum number of questions per mandatory skill and an overall question budget.
* Selection: first guarantee minimum coverage of every mandatory skill (prerequisite skills
  first, then by importance), then spend the remaining budget where uncertainty x
  importance is highest. Difficulty moves up after a correct answer and down after a
  wrong one (a staircase), starting from the provisional skill profile.
* Rotation: among eligible questions, prefer those this workspace has seen least.
* Answer-key protection (pattern from QuizBlitz): clients only ever receive a public
  projection of the current question; only the question currently served can be
  answered, once; timing is measured on the server; correct answers and explanations
  are revealed only after the attempt is finished.
* Scoring: objective questions are scored deterministically. Subjective (practical)
  answers are scored only by a rubric-driven AI evaluator with validated output; when
  none is available they are recorded but excluded from proficiency.
* Reporting: proficiency, accuracy, difficulty performance, coverage and confidence are
  reported separately; fewer than 2 scored answers gives "insufficient" confidence and
  no numeric proficiency.
"""

import hashlib
import re
from datetime import timedelta

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm import AIUnavailable, run_task, untrusted
from app.config import get_settings
from app.db import as_utc, utcnow
from app.errors import api_error
from app.models import (
    AssessmentAttempt,
    AssessmentBlueprint,
    AssessmentQuestion,
    AssessmentResponse,
    CareerTransition,
    ProficiencyHistory,
    SkillEvidence,
)
from app.services.evidence import METHOD_VERSION, claimed_scores, estimate, latest_assessed, level_for
from app.services.scoring import SKILL_CATEGORIES, current_job
from app.services.taxonomy import SKILL_BY_ID, prerequisites, skill_name

ENGINE_VERSION = "adaptive-v1"
DIFF_WEIGHT = {1: 1.0, 2: 1.5, 3: 2.0}
DIFF_CAP = {1: 60.0, 2: 85.0, 3: 100.0}  # highest difficulty attempted caps the estimate
OBJECTIVE = {"single", "multi", "code_output", "short_answer", "scenario"}
TIMER_GRACE_SECONDS = 2
QUIZ_EXCLUDED_CATEGORIES = {"professional"}  # assessed via interviews and projects instead


# ----------------------------------------------------------------------------- helpers


def normalize_answer(s: str) -> str:
    s = s.strip().lower().replace(",", " ").replace("|", " ").replace("'", "").replace('"', "")
    s = re.sub(r"\s*([\[\](){}])\s*", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def confidence_for(n: int) -> str:
    if n < 2:
        return "insufficient"
    if n <= 3:
        return "low"
    if n <= 5:
        return "medium"
    return "high"


def subjective_available() -> bool:
    return get_settings().provider_for("answer_evaluation") != "rules"


def _bank(db: Session, workspace_id: str, skill_id: str) -> list[AssessmentQuestion]:
    qs = db.scalars(select(AssessmentQuestion).where(
        AssessmentQuestion.skill_id == skill_id, AssessmentQuestion.validated,
        (AssessmentQuestion.workspace_id.is_(None)) | (AssessmentQuestion.workspace_id == workspace_id))).all()
    if not subjective_available():
        qs = [q for q in qs if q.qtype in OBJECTIVE]
    return list(qs)


def public_question(q: AssessmentQuestion) -> dict:
    """The only representation of a question that ever leaves the server mid-attempt."""
    return {"id": q.id, "skill_id": q.skill_id, "skill_name": skill_name(q.skill_id), "topic": q.topic, "difficulty": q.difficulty,
            "type": q.qtype, "prompt": q.prompt, "code": q.code, "choices": q.choices,
            "select_multiple": q.qtype == "multi", "free_text": q.qtype in ("code_output", "short_answer", "practical")}


# ----------------------------------------------------------------------------- AI question generation


class GenQuestion(BaseModel):
    qtype: str = Field(description="single | multi")
    difficulty: int = Field(ge=1, le=3)
    topic: str
    prompt: str
    choices: list[str] = Field(min_length=3, max_length=5)
    correct: list[int] = Field(min_length=1)
    explanation: str
    learning_objective: str

    @field_validator("qtype")
    @classmethod
    def _t(cls, v: str) -> str:
        if v not in ("single", "multi"):
            raise ValueError("qtype must be single or multi")
        return v


class GenBatch(BaseModel):
    questions: list[GenQuestion] = Field(max_length=6)


GEN_PROMPT_VERSION = "question-gen-v1"


def _valid_generated(q: GenQuestion) -> bool:
    if len({c.strip().lower() for c in q.choices}) != len(q.choices):
        return False
    if any(i < 0 or i >= len(q.choices) for i in q.correct) or len(set(q.correct)) != len(q.correct):
        return False
    if q.qtype == "single" and len(q.correct) != 1:
        return False
    return bool(q.explanation.strip()) and len(q.prompt) > 15


def generate_questions(db: Session, workspace_id: str, is_guest: bool, skill_id: str, job_excerpt: str | None) -> int:
    """Ask the configured AI provider for questions on a skill the curated bank lacks.
    Only structurally valid questions are stored; they are labelled as AI-generated."""
    if get_settings().provider_for("question_generation") == "rules":
        return 0
    name = skill_name(skill_id)
    system = ("You write multiple-choice diagnostic questions that test practical, job-relevant knowledge of one skill. "
              "Each question must have exactly the stated correct answers, plausible distractors and a short explanation. "
              "Do not ask trivia about product versions or prices.")
    user = f"Skill: {name}\nWrite 4 questions: two easy, one medium and one hard.\n" + (
        untrusted("job_requirement", job_excerpt) if job_excerpt else "")
    try:
        res = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="question_generation", prompt_version=GEN_PROMPT_VERSION,
                       system=system, user=user, schema=GenBatch, rules=None)
    except AIUnavailable:
        return 0
    stored = 0
    for q in res.data.questions:
        if not _valid_generated(q):
            continue
        qid = f"gen-{skill_id}-{hashlib.sha1((workspace_id + q.prompt).encode()).hexdigest()[:10]}"
        if db.get(AssessmentQuestion, qid):
            continue
        db.add(AssessmentQuestion(
            id=qid, workspace_id=workspace_id, skill_id=skill_id, topic=q.topic[:120], competency=f"Apply {name}",
            difficulty=q.difficulty, qtype=q.qtype, prompt=q.prompt, choices=q.choices,
            correct_answer=q.correct[0] if q.qtype == "single" else sorted(q.correct), explanation=q.explanation,
            learning_objective=q.learning_objective, origin="generated", validated=True, model_id=res.model,
            prompt_version=GEN_PROMPT_VERSION,
            validation_source=f"AI-generated ({res.model}); structurally validated, not expert-reviewed"))
        stored += 1
    db.flush()
    return stored


# ----------------------------------------------------------------------------- blueprint


def build_blueprint(db: Session, t: CareerTransition, *, is_guest: bool, kind: str, skill_id: str | None = None) -> AssessmentBlueprint:
    job = current_job(db, t.id)
    if job is None:
        raise api_error(409, "NO_JOB", "Add a target job first so the assessment can focus on what the role needs.")
    assessed = latest_assessed(db, t.workspace_id)
    claimed = claimed_scores(db, t.workspace_id)
    reqs = {}
    for r in job.requirements:
        if r.skill_id and r.category in SKILL_CATEGORIES and r.skill_id not in reqs:
            reqs[r.skill_id] = r
    if kind == "topic_check":
        if not skill_id or skill_id not in SKILL_BY_ID:
            raise api_error(422, "UNKNOWN_SKILL", "Choose a skill to check.")
        targets = [(skill_id, reqs[skill_id].importance if skill_id in reqs else "mandatory", reqs.get(skill_id))]
    else:
        targets = [(sid, r.importance, r) for sid, r in reqs.items()]

    items, uncovered = [], []
    for sid, importance, req in targets:
        if SKILL_BY_ID[sid]["category"] in QUIZ_EXCLUDED_CATEGORIES:
            uncovered.append({"skill_id": sid, "name": skill_name(sid), "importance": importance,
                              "reason": "Assessed through mock interviews and projects rather than a quiz."})
            continue
        bank = _bank(db, t.workspace_id, sid)
        if len(bank) < 2:
            generate_questions(db, t.workspace_id, is_guest, sid, req.source_excerpt if req else None)
            bank = _bank(db, t.workspace_id, sid)
        if not bank:
            uncovered.append({"skill_id": sid, "name": skill_name(sid), "importance": importance,
                              "reason": "No validated questions are available yet; use a practical project to evidence this skill."})
            continue
        est = estimate(sid, assessed, claimed)
        start = 3 if est["score"] >= 70 else 2 if est["score"] >= 45 else 1
        minimum = 3 if kind == "topic_check" else (2 if importance == "mandatory" else 1)
        items.append({"skill_id": sid, "name": skill_name(sid), "importance": importance,
                      "weight": 3.0 if importance == "mandatory" else 1.0, "min_questions": min(minimum, len(bank)),
                      "available": len(bank), "start_difficulty": start, "prior_basis": est["basis"],
                      "prerequisites": [p for p in prerequisites(sid) if p in {x[0] for x in targets}]})
    if not items:
        raise api_error(409, "NOTHING_TO_ASSESS", "None of this job's skills can be assessed by quiz yet.", uncovered=uncovered)
    need = sum(i["min_questions"] for i in items)
    if kind == "topic_check":
        budget = min(4, sum(i["available"] for i in items))
    else:
        extra = sum(1 for i in items if i["importance"] == "mandatory")
        budget = max(need, min(30, max(8, need + extra)))
        budget = min(budget, sum(i["available"] for i in items))
    bp = AssessmentBlueprint(workspace_id=t.workspace_id, transition_id=t.id, kind=kind, items=items,
                             question_budget=max(budget, need), uncovered=uncovered, engine_version=ENGINE_VERSION)
    db.add(bp)
    db.flush()
    return bp


# ----------------------------------------------------------------------------- selection


def _skill_state(state: dict, sid: str, start: int) -> dict:
    return state.setdefault("skills", {}).setdefault(
        sid, {"n": 0, "correct": 0, "w_score": 0.0, "w_total": 0.0, "level": start, "max_diff": 0, "by_diff": {}})


def _exposures(db: Session, workspace_id: str, qids: list[str]) -> dict[str, int]:
    rows = db.execute(select(AssessmentResponse.question_id, func.count()).where(
        AssessmentResponse.workspace_id == workspace_id, AssessmentResponse.question_id.in_(qids))
        .group_by(AssessmentResponse.question_id)).all()
    return dict(rows)  # type: ignore[arg-type]


def select_next(db: Session, attempt: AssessmentAttempt, bp: AssessmentBlueprint) -> AssessmentQuestion | None:
    state = attempt.state
    asked = set(state.get("asked", []))
    if len(asked) >= bp.question_budget:
        return None
    items = {i["skill_id"]: i for i in bp.items}
    pools = {sid: [q for q in _bank(db, attempt.workspace_id, sid) if q.id not in asked] for sid in items}
    open_items = [i for i in bp.items if pools[i["skill_id"]]]
    if not open_items:
        return None

    def st(i):  # read-only view; selection must not mutate attempt state
        return state.get("skills", {}).get(i["skill_id"]) or {"n": 0, "correct": 0, "level": i["start_difficulty"]}

    below_min = [i for i in open_items if st(i)["n"] + _pending(state, i["skill_id"]) < i["min_questions"]]
    if below_min:
        uncovered_ids = {i["skill_id"] for i in below_min}
        # Prerequisites first: defer a skill while one of its prerequisites is still uncovered.
        ready = [i for i in below_min if not any(p in uncovered_ids for p in i["prerequisites"])] or below_min
        chosen = sorted(ready, key=lambda i: (-i["weight"], st(i)["n"], i["skill_id"]))[0]
    else:
        if state.get("stop_when_confident", True) and all(confidence_for(st(i)["n"]) in ("medium", "high") for i in bp.items):
            return None

        def priority(i):
            s = st(i)
            acc = s["correct"] / s["n"] if s["n"] else 0.5
            uncertainty = 1 / (1 + s["n"]) + (0.5 if 0.3 <= acc <= 0.7 else 0)
            return (-i["weight"] * uncertainty, i["skill_id"])

        chosen = sorted(open_items, key=priority)[0]

    s = st(chosen)
    target = s["level"]
    # A weak prerequisite result pulls the dependent skill back to the easiest questions.
    for p in chosen["prerequisites"]:
        ps = state.get("skills", {}).get(p)
        if ps and ps["n"] >= 2 and ps["correct"] / ps["n"] < 0.5:
            target = 1
    pool = pools[chosen["skill_id"]]
    seen = _exposures(db, attempt.workspace_id, [q.id for q in pool])
    salt = attempt.id
    # Cost: distance from the target difficulty, plus a penalty per previous exposure, so an
    # unseen question one step away is preferred over repeating an exact-difficulty one.
    pool.sort(key=lambda q: (abs(q.difficulty - target) + 1.5 * min(seen.get(q.id, 0), 2),
                             hashlib.sha1((salt + q.id).encode()).hexdigest()))
    return pool[0]


def _pending(state: dict, sid: str) -> int:
    """Answers served but excluded from scoring (e.g. unevaluated practical) still count towards coverage."""
    return state.get("unscored", {}).get(sid, 0)


def serve(db: Session, attempt: AssessmentAttempt, q: AssessmentQuestion) -> None:
    prior = db.scalar(select(func.count(AssessmentResponse.id)).where(
        AssessmentResponse.workspace_id == attempt.workspace_id, AssessmentResponse.question_id == q.id)) or 0
    attempt.current_question_id = q.id
    attempt.current_served_at = utcnow()
    attempt.state = {**attempt.state, "asked": [*attempt.state.get("asked", []), q.id]}
    db.add(AssessmentResponse(workspace_id=attempt.workspace_id, attempt_id=attempt.id, question_id=q.id, skill_id=q.skill_id,
                              difficulty=q.difficulty, served_at=attempt.current_served_at, repeat_exposure=prior > 0))


# ----------------------------------------------------------------------------- scoring


class RubricEval(BaseModel):
    criteria: dict[str, int] = Field(description="criterion id -> score 1..5")
    feedback: str


def score_response(db: Session, q: AssessmentQuestion, response, *, workspace_id: str, is_guest: bool) -> tuple[float | None, bool | None, dict | None, str]:
    if q.qtype in ("single", "scenario"):
        if not isinstance(response, int) or isinstance(response, bool) or not 0 <= response < len(q.choices):
            raise api_error(422, "INVALID_ANSWER", "Choose one of the options.")
        ok = response == q.correct_answer
        return (1.0 if ok else 0.0), ok, None, "deterministic"
    if q.qtype == "multi":
        if not isinstance(response, list) or not response or len(set(response)) != len(response) or \
                not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(q.choices) for i in response):
            raise api_error(422, "INVALID_ANSWER", "Choose one or more of the options.")
        correct = set(q.correct_answer)
        chosen = set(response)
        partial = max(0.0, (len(chosen & correct) - len(chosen - correct)) / len(correct))
        return round(partial, 3), chosen == correct, None, "deterministic"
    if not isinstance(response, str) or not response.strip() or len(response) > 5000:
        raise api_error(422, "INVALID_ANSWER", "Type your answer (up to 5000 characters).")
    if q.qtype in ("code_output", "short_answer") and q.correct_answer:
        ok = normalize_answer(response) in {normalize_answer(a) for a in q.correct_answer["accepted"]}
        return (1.0 if ok else 0.0), ok, None, "deterministic"
    # practical / open-ended: rubric evaluation by AI only
    if not subjective_available() or not q.rubric:
        return None, None, {"status": "not_evaluated", "reason": "Open answers need an AI evaluator, which is not configured."}, "not_evaluated"
    ids = [c["id"] for c in q.rubric["criteria"]]
    system = ("You grade a candidate's answer against a fixed rubric. Score each criterion 1 (absent) to 5 (excellent) "
              "using only what the answer says. Give brief, specific feedback.")
    user = (f"Question: {q.prompt}\nRubric criteria: " + "; ".join(f"{c['id']}: {c['description']}" for c in q.rubric["criteria"])
            + "\n" + untrusted("candidate_answer", response))

    def check(out: RubricEval) -> RubricEval:
        if set(out.criteria) != set(ids) or not all(1 <= v <= 5 for v in out.criteria.values()):
            raise ValueError("rubric mismatch")
        return out

    try:
        res = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="answer_evaluation", prompt_version="rubric-eval-v1",
                       system=system, user=user, schema=RubricEval, rules=None, validate=check)
    except (AIUnavailable, ValueError):
        return None, None, {"status": "not_evaluated", "reason": "The evaluator was unavailable; this answer is saved but not scored."}, "not_evaluated"
    weights = {c["id"]: c.get("weight", 1) for c in q.rubric["criteria"]}
    score = sum(weights[k] * (v - 1) / 4 for k, v in res.data.criteria.items()) / sum(weights.values())
    return round(score, 3), score >= 0.7, {"criteria": res.data.criteria, "feedback": res.data.feedback, "model": res.model}, "llm_rubric"


def apply_to_state(state: dict, item: dict, q: AssessmentQuestion, score: float | None, repeat: bool) -> dict:
    state = {**state, "skills": dict(state.get("skills", {})), "unscored": dict(state.get("unscored", {}))}
    s = dict(_skill_state(state, q.skill_id, item["start_difficulty"]))
    if score is None:
        state["unscored"][q.skill_id] = state["unscored"].get(q.skill_id, 0) + 1
        return state
    w = DIFF_WEIGHT[q.difficulty] * (0.5 if repeat else 1.0)
    s["n"] += 1
    s["correct"] += 1 if score >= 0.99 else 0
    s["w_score"] += w * score
    s["w_total"] += w
    s["max_diff"] = max(s["max_diff"], q.difficulty)
    bd = dict(s["by_diff"])
    d = bd.get(str(q.difficulty), {"asked": 0, "correct": 0})
    bd[str(q.difficulty)] = {"asked": d["asked"] + 1, "correct": d["correct"] + (1 if score >= 0.99 else 0)}
    s["by_diff"] = bd
    s["level"] = min(3, s["level"] + 1) if score >= 0.99 else max(1, s["level"] - 1) if score < 0.5 else s["level"]
    state["skills"][q.skill_id] = s
    return state


# ----------------------------------------------------------------------------- lifecycle


def time_left(attempt: AssessmentAttempt) -> int | None:
    if not attempt.timed or not attempt.current_served_at:
        return None
    deadline = as_utc(attempt.current_served_at) + timedelta(seconds=attempt.seconds_per_question or 60)
    return max(0, int((deadline - utcnow()).total_seconds()))


def answer(db: Session, attempt: AssessmentAttempt, question_id: str, response, *, is_guest: bool) -> None:
    if attempt.status != "in_progress":
        raise api_error(409, "ATTEMPT_CLOSED", "This assessment is already finished.")
    if attempt.current_question_id != question_id:
        raise api_error(409, "QUESTION_CLOSED", "That question is not open. Reload to continue.")
    q = db.get(AssessmentQuestion, question_id)
    resp = db.scalar(select(AssessmentResponse).where(AssessmentResponse.attempt_id == attempt.id, AssessmentResponse.question_id == question_id))
    if q is None or resp is None or resp.answered_at is not None:
        raise api_error(409, "ALREADY_ANSWERED", "That question was already answered.")
    now = utcnow()
    late = attempt.timed and now > as_utc(attempt.current_served_at) + timedelta(seconds=(attempt.seconds_per_question or 60) + TIMER_GRACE_SECONDS)  # type: ignore[operator]
    if late:
        score, ok, evaluation, method = 0.0, False, {"status": "timed_out"}, "deterministic"
        resp.timed_out = True
    else:
        score, ok, evaluation, method = score_response(db, q, response, workspace_id=attempt.workspace_id, is_guest=is_guest)
    resp.response, resp.answered_at, resp.score, resp.is_correct = response, now, score, ok
    resp.evaluation, resp.evaluation_method = evaluation, method
    bp = db.get(AssessmentBlueprint, attempt.blueprint_id)
    item = next(i for i in bp.items if i["skill_id"] == q.skill_id)  # type: ignore[union-attr]
    attempt.state = apply_to_state(attempt.state, item, q, score, resp.repeat_exposure)
    attempt.current_question_id = None
    attempt.current_served_at = None
    attempt.version += 1


def coverage(attempt: AssessmentAttempt, bp: AssessmentBlueprint) -> dict:
    skills = attempt.state.get("skills", {})
    unscored = attempt.state.get("unscored", {})
    per = {i["skill_id"]: skills.get(i["skill_id"], {}).get("n", 0) + unscored.get(i["skill_id"], 0) for i in bp.items}
    mandatory = [i for i in bp.items if i["importance"] == "mandatory"]
    missing = [i["skill_id"] for i in mandatory if per[i["skill_id"]] < i["min_questions"]]
    return {"skills_covered": sum(1 for i in bp.items if per[i["skill_id"]] >= i["min_questions"]), "skills_total": len(bp.items),
            "mandatory_complete": not missing, "mandatory_missing": missing,
            "answered": len([q for q in attempt.state.get("asked", [])]) - (1 if attempt.current_question_id else 0),
            "budget": bp.question_budget}


def finish(db: Session, attempt: AssessmentAttempt, bp: AssessmentBlueprint, *, force: bool = False) -> dict:
    cov = coverage(attempt, bp)
    if not cov["mandatory_complete"] and not force:
        # Only allow finishing early when no questions remain for the uncovered skills.
        if select_next(db, attempt, bp) is not None:
            raise api_error(409, "COVERAGE_INCOMPLETE", "Answer a few more questions so every required skill is covered.",
                            missing=[skill_name(s) for s in cov["mandatory_missing"]])
    if attempt.current_question_id:  # abandon the unanswered open question
        attempt.current_question_id = None
    results = {}
    now = utcnow()
    for item in bp.items:
        sid = item["skill_id"]
        s = attempt.state.get("skills", {}).get(sid, {"n": 0, "correct": 0, "w_score": 0, "w_total": 0, "max_diff": 0, "by_diff": {}})
        conf = confidence_for(s["n"])
        score = None
        if conf != "insufficient" and s["w_total"]:
            score = round(100 * (s["w_score"] / s["w_total"]) * DIFF_CAP[max(1, s["max_diff"])] / 100, 1)
        accuracy = round(s["correct"] / s["n"], 3) if s["n"] else None
        results[sid] = {"name": skill_name(sid), "importance": item["importance"], "score": score, "level": level_for(score),
                        "confidence": conf, "answered": s["n"], "accuracy": accuracy, "difficulty": s["by_diff"],
                        "highest_difficulty": s["max_diff"], "unscored_answers": attempt.state.get("unscored", {}).get(sid, 0)}
        db.add(ProficiencyHistory(workspace_id=attempt.workspace_id, skill_id=sid, score=score, level=level_for(score), confidence=conf,
                                  questions_answered=s["n"], accuracy=accuracy, difficulty_breakdown=s["by_diff"],
                                  evidence_summary={"attempt_kind": attempt.kind, "engine": ENGINE_VERSION},
                                  methodology=METHOD_VERSION, source_ref=attempt.id, created_at=now))
        if s["n"]:
            db.add(SkillEvidence(workspace_id=attempt.workspace_id, skill_id=sid, evidence_type="quiz", source_ref=attempt.id,
                                 score=score, confidence={"insufficient": 0.1, "low": 0.4, "medium": 0.6, "high": 0.8}[conf],
                                 methodology=ENGINE_VERSION, excerpt=f"{s['correct']}/{s['n']} correct"))
    scored = sum(r["answered"] for r in results.values())
    correct = sum(attempt.state.get("skills", {}).get(sid, {}).get("correct", 0) for sid in results)
    attempt.results = {
        "skills": results, "coverage": cov, "uncovered": bp.uncovered,
        "overall": {"answered": scored, "correct": correct, "accuracy": round(correct / scored, 3) if scored else None},
        "engine_version": ENGINE_VERSION,
        "disclaimer": ("These estimates come from a short adaptive quiz. They guide your learning plan; they are not a "
                       "validated measure of professional competence."),
    }
    attempt.status = "completed"
    attempt.completed_at = now
    attempt.version += 1
    return attempt.results


def review(db: Session, attempt: AssessmentAttempt) -> list[dict]:
    if attempt.status != "completed":
        raise api_error(409, "NOT_FINISHED", "Answers are shown after you finish the assessment.")
    out = []
    for r in db.scalars(select(AssessmentResponse).where(AssessmentResponse.attempt_id == attempt.id).order_by(AssessmentResponse.served_at)):
        q = db.get(AssessmentQuestion, r.question_id)
        out.append({**public_question(q), "your_answer": r.response, "correct_answer": q.correct_answer,  # type: ignore[arg-type]
                    "explanation": q.explanation, "is_correct": r.is_correct, "score": r.score, "timed_out": r.timed_out,  # type: ignore[union-attr]
                    "evaluation": r.evaluation, "validation_source": q.validation_source, "origin": q.origin})  # type: ignore[union-attr]
    return out
