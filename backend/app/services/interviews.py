"""Mock interviews scored with one stable rubric (interview-rubric-v1).

Evaluators: an AI provider (schema-validated) when configured, otherwise a transparent
heuristic that looks for structure, specifics and reasoning signals. The method is always
reported. Feedback never invents experience: example outlines use [placeholders]."""

import re

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.llm import run_task, untrusted
from app.models import CareerTransition, InterviewEvaluation
from app.seed.interviews import QUESTIONS, RUBRIC, RUBRIC_VERSION
from app.seed.skills import role_family

QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
CRITERIA = [c["id"] for c in RUBRIC]
STOP = set("the a an and or to of in on for with your you how what why would do did tell me about time when is are be it this that".split())


def pick_questions(db: Session, t: CareerTransition, gap_skills: list[str], n: int = 5) -> list[str]:
    family = role_family(t.target_role)
    asked = dict(db.execute(select(InterviewEvaluation.question_id, func.count()).where(InterviewEvaluation.workspace_id == t.workspace_id)
                            .group_by(InterviewEvaluation.question_id)).all())

    def key(q):
        return (asked.get(q["id"], 0), 0 if q["competency"] in gap_skills else 1, q["id"])

    general = sorted([q for q in QUESTIONS if q["family"] == "general"], key=key)
    specific = sorted([q for q in QUESTIONS if q["family"] == family], key=key)
    chosen = general[:2] + specific[: n - 3] + [q for q in general[2:] if q["type"] == "scenario"][:1]
    for q in general[2:] + specific:
        if len(chosen) >= n:
            break
        if q not in chosen:
            chosen.append(q)
    return [q["id"] for q in chosen[:n]]


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z][a-z'+#.-]*", s.lower())


def heuristic_eval(question: dict, answer: str) -> dict:
    words = _words(answer)
    n = len(words)
    qwords = {w for w in _words(question["text"]) if w not in STOP and len(w) > 3}
    overlap = len(qwords & set(words)) / max(1, len(qwords))
    has_numbers = bool(re.search(r"\d", answer))
    star = {
        "situation": bool(re.search(r"\b(when i|at my|in my (last|previous|current)|situation|context|we had|our team)\b", answer, re.I)),
        "task": bool(re.search(r"\b(my (goal|task|job|role) was|i needed to|i had to|responsible for)\b", answer, re.I)),
        "action": len(re.findall(r"\bi (built|created|decided|analysed|analyzed|led|asked|organised|organized|wrote|met|spoke|set up|designed|tested|checked|used|started|changed|proposed)\b", answer, re.I)) >= 1,
        "result": bool(re.search(r"\b(result|as a result|outcome|which led|so that|improved|reduced|increased)\b", answer, re.I)) or has_numbers,
    }
    steps = len(re.findall(r"\b(first|second|then|next|after that|finally|step)\b", answer, re.I))
    reasoning = len(re.findall(r"\b(because|so that|trade-?off|however|instead|which means|depends|risk)\b", answer, re.I))
    sentences = max(1, len(re.findall(r"[.!?]", answer)))
    avg_len = n / sentences

    relevance = 1 + min(4, round(overlap * 6))
    structure = 1 + (sum(star.values()) if question["type"] == "behavioral" else min(4, steps + (1 if sentences >= 3 else 0)))
    evidence = 1 + min(4, (2 if has_numbers else 0) + (1 if re.search(r"\b(for example|for instance|e\.g\.)\b", answer, re.I) else 0) + (1 if star["action"] else 0))
    depth = 1 + min(4, reasoning + (1 if n > 120 else 0))
    if 80 <= n <= 350 and avg_len <= 30:
        communication = 5
    elif 40 <= n <= 450:
        communication = 3
    else:
        communication = 2 if n >= 15 else 1
    scores = {"relevance": relevance, "structure": min(5, structure), "evidence": evidence, "depth": depth, "communication": communication}

    strengths, improvements = [], []
    if scores["structure"] >= 4:
        strengths.append("Clear structure that is easy to follow.")
    if has_numbers:
        strengths.append("Uses concrete numbers or outcomes.")
    if reasoning:
        strengths.append("Explains the reasoning behind decisions.")
    if question["type"] == "behavioral":
        for part, ok in star.items():
            if not ok:
                improvements.append(f"Add the {part} part of the STAR structure.")
    if not has_numbers:
        improvements.append("Where true, add a measurable result (time saved, % improvement, number of people).")
    if n < 80:
        improvements.append("Expand your answer; aim for roughly 1-2 minutes when spoken.")
    if n > 350:
        improvements.append("Tighten the answer; aim for roughly 1-2 minutes when spoken.")
    if relevance <= 2:
        improvements.append("Answer the question more directly; restate it in your first sentence.")
    return {"criteria": scores, "strengths": strengths or ["You answered the question."], "improvements": improvements[:4],
            "outline": outline(question)}


def outline(question: dict) -> list[str]:
    if question["type"] == "behavioral":
        return ["Situation: [where you were and what was happening]", "Task: [what you were responsible for]",
                "Action: [the specific steps you took]", "Result: [what changed, with a number if you have one]",
                "Reflection: [what you would repeat or do differently]"]
    return ["Restate the problem in one sentence", "Explain your approach step by step", "Mention a trade-off or risk",
            "Say how you would check that it worked"]


class LLMInterviewEval(BaseModel):
    criteria: dict[str, int] = Field(description="relevance, structure, evidence, depth, communication: 1-5 each")
    strengths: list[str] = Field(max_length=4)
    improvements: list[str] = Field(max_length=4)


SYSTEM = ("You are an interview coach. Score the answer on the rubric (1-5 each) using only what the candidate wrote. "
          "Give specific strengths and improvements. Never invent experience, employers or numbers for the candidate; "
          "suggest what kind of detail to add instead.")


def evaluate(db: Session, *, workspace_id: str, is_guest: bool, question: dict, answer: str, role: str) -> tuple[dict, str, str | None]:
    def rules() -> LLMInterviewEval:
        h = heuristic_eval(question, answer)
        return LLMInterviewEval(criteria=h["criteria"], strengths=h["strengths"], improvements=h["improvements"])

    def check(out: LLMInterviewEval) -> LLMInterviewEval:
        if set(out.criteria) != set(CRITERIA) or not all(1 <= v <= 5 for v in out.criteria.values()):
            raise ValueError("rubric mismatch")
        return out

    rubric = "; ".join(f"{c['id']}: {c['description']}" for c in RUBRIC)
    res = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="interview_feedback", prompt_version="interview-eval-v1",
                   system=SYSTEM, user=f"Role: {role}\nQuestion ({question['type']}): {question['text']}\nRubric: {rubric}\n"
                   + untrusted("candidate_answer", answer), schema=LLMInterviewEval, rules=rules, validate=check)
    method = "ai_rubric" if res.method == "llm" else "heuristic_rubric"
    return ({"criteria": res.data.criteria, "strengths": res.data.strengths, "improvements": res.data.improvements,
             "outline": outline(question), "rubric_version": RUBRIC_VERSION}, method, res.model)


def overall(criteria: dict[str, int]) -> float:
    return round(sum((v - 1) / 4 for v in criteria.values()) / len(criteria) * 100, 1)
