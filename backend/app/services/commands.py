"""Natural-language commands (Wispr Flow-compatible: any dictated or typed text).

Flow: interpret(text) -> proposed structured action -> validated -> shown to the user ->
confirmed -> execute(action) through the same backend rules as the normal endpoints ->
actual result returned. Interpretation is rule-based by default; an AI provider, when
configured, can propose an action, which then goes through the same validation.
"""

import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm import AIUnavailable, run_task, untrusted
from app.models import CareerTransition, JobApplication, LearningPlan, PlanTask
from app.services.taxonomy import find_skills, skill_name

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
ACTIONS = {"set_weekly_hours", "set_deadline", "set_budget", "set_target_role", "complete_task", "add_application",
           "update_application_status", "start_topic_check", "regenerate_plan"}


class Proposal(BaseModel):
    type: str
    params: dict[str, Any]


def _num(s: str) -> float | None:
    s = s.strip().lower()
    if s in NUM_WORDS:
        return float(NUM_WORDS[s])
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    t = text.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\bin (\w+) (week|weeks|month|months)\b", t)
    if m and _num(m[1]):
        n = int(_num(m[1]))  # type: ignore[arg-type]
        if m[2].startswith("week"):
            return today + timedelta(weeks=n)
        y, mo = divmod(today.month - 1 + n, 12)
        last = (date(today.year + y + (mo == 11), (mo + 1) % 12 + 1, 1) - timedelta(days=1)).day
        return date(today.year + y, mo + 1, min(today.day, last))
    month_re = "|".join(MONTHS + [mo[:3] for mo in MONTHS])
    m = re.search(rf"\b(?:(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?)?({month_re})\.?(?:\s+(\d{{1,2}})(?:st|nd|rd|th)?)?(?:,?\s+(\d{{4}}))?\b", t)
    if m and (m[1] or m[3] or m[4] or "end of" in t or "by" in t):
        mi = next(i for i, mo in enumerate(MONTHS) if mo.startswith(m[2][:3])) + 1
        day = int(m[1] or m[3] or 0)
        year = int(m[4]) if m[4] else today.year
        if not day:
            nxt = date(year + (mi == 12), mi % 12 + 1, 1)
            d = nxt - timedelta(days=1)
        else:
            d = date(year, mi, min(day, 28 if mi == 2 else 30 if mi in (4, 6, 9, 11) else 31))
        if not m[4] and d <= today:
            d = d.replace(year=d.year + 1)
        return d
    return None


def parse_rules(text: str) -> Proposal | None:
    t = text.strip()
    low = t.lower()
    m = re.search(r"(\d+(?:\.\d+)?|\b(?:" + "|".join(NUM_WORDS) + r")\b)\s*(?:hours?|hrs?|h)\b[^.]*?\b(?:a|per|each|every)\s*week", low) or \
        re.search(r"\bweek(?:ly)?\b[^.]*?(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)", low)
    if m and re.search(r"\b(study|hours|available|can|have|weekly|per week|a week)\b", low):
        return Proposal(type="set_weekly_hours", params={"hours": _num(m.group(1))})
    if re.search(r"\b(deadline|ready by|finish by|done by|target date)\b", low):
        d = parse_date(low)
        if d:
            return Proposal(type="set_deadline", params={"deadline": d.isoformat()})
    if re.search(r"\b(no budget|free (resources|courses) only|only free|can't spend|cannot spend)\b", low):
        return Proposal(type="set_budget", params={"amount": 0, "currency": None})
    m = re.search(r"\b(?:budget|spend)\b[^\d$£€]*([$£€])?\s*(\d+(?:\.\d+)?)\s*(dollars|usd|pounds|gbp|euros?|eur|rupees|inr)?", low)
    if m:
        cur = {"$": "USD", "£": "GBP", "€": "EUR"}.get(m[1] or "", None) or {"dollars": "USD", "usd": "USD", "pounds": "GBP", "gbp": "GBP",
                                                                          "euro": "EUR", "euros": "EUR", "eur": "EUR", "rupees": "INR", "inr": "INR"}.get(m[3] or "")
        return Proposal(type="set_budget", params={"amount": float(m[2]), "currency": cur})
    m = re.search(r"\b(?:i want to (?:become|be|work as)|change my target(?: role)? to|switch (?:my goal |my target )?to|target role (?:is|to))\s+(?:an?\s+)?([a-z][a-z /&-]{2,60})", low)
    if m:
        return Proposal(type="set_target_role", params={"role": m[1].strip(" .").title()})
    m = re.search(r"\b(?:quiz|test|check|assess)\s+me\s+(?:on|in)\s+(.+)", low)
    if m:
        skills = list(find_skills(m[1]))
        if skills:
            return Proposal(type="start_topic_check", params={"skill_id": skills[0]})
    if re.search(r"\b(regenerate|rebuild|redo|update|refresh) (my )?(learning )?plan\b", low):
        return Proposal(type="regenerate_plan", params={})
    m = re.search(r"\bi (?:just )?applied (?:to|for) (?:an? |the )?(.+?) (?:role |position |job )?(?:at|with) ([a-z0-9][\w&.' -]{1,60})", low)
    if m:
        return Proposal(type="add_application", params={"role_title": m[1].strip().title(), "company": m[2].strip(" .").title(), "status": "applied"})
    m = re.search(r"\b([a-z0-9][\w&.' -]{1,60}?) (?:rejected me|turned me down|sent (?:me )?a rejection|said no)", low)
    if m:
        return Proposal(type="update_application_status", params={"company": m[1].strip().title(), "status": "rejected"})
    m = re.search(r"\b(?:got|have|booked|scheduled) an? (?:interview|screen(?:ing)?(?: call)?) (?:with|at) ([a-z0-9][\w&.' -]{1,60})", low)
    if m:
        status = "screening" if "screen" in low else "interview"
        return Proposal(type="update_application_status", params={"company": m[1].strip(" .").title(), "status": status})
    m = re.search(r"\b(?:got|received) an? offer (?:from|at) ([a-z0-9][\w&.' -]{1,60})", low)
    if m:
        return Proposal(type="update_application_status", params={"company": m[1].strip(" .").title(), "status": "offer"})
    m = re.search(r"\b(?:i )?(?:finished|completed|done with|did|mark(?:ed)?)\s+(?:the |my )?(.+?)(?: as (?:done|complete|completed))?[.!]?$", low)
    if m:
        return Proposal(type="complete_task", params={"query": m[1].strip()})
    return None


class LLMProposal(BaseModel):
    type: str
    params: dict[str, Any]


def interpret_ai(db: Session, *, workspace_id: str, is_guest: bool, text: str) -> Proposal | None:
    system = ("Convert the user's request into one action for a career-planning app. Allowed types: " + ", ".join(sorted(ACTIONS))
              + ". Params: set_weekly_hours{hours}, set_deadline{deadline YYYY-MM-DD}, set_budget{amount,currency}, set_target_role{role}, "
              "complete_task{query}, add_application{company,role_title,status}, update_application_status{company,status}, "
              "start_topic_check{skill}, regenerate_plan{}. If nothing fits, use type 'none'.")
    try:
        res = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="command_parsing", prompt_version="command-v1",
                       system=system, user=untrusted("dictated_text", text), schema=LLMProposal, rules=None)
    except AIUnavailable:
        return None
    if res.data.type not in ACTIONS:
        return None
    p = dict(res.data.params)
    if res.data.type == "start_topic_check" and "skill" in p:
        p = {"skill_id": next(iter(find_skills(str(p["skill"]))), None)}
    return Proposal(type=res.data.type, params=p)


def _find_task(db: Session, t: CareerTransition, query: str) -> PlanTask | None:
    plan = db.scalar(select(LearningPlan).where(LearningPlan.transition_id == t.id))
    if not plan or not plan.current_version_id:
        return None
    pending = list(db.scalars(select(PlanTask).where(PlanTask.plan_version_id == plan.current_version_id, PlanTask.status != "completed",
                                                     PlanTask.week_number > 0).order_by(PlanTask.scheduled_date, PlanTask.day_number)))
    if not pending:
        return None
    if re.search(r"\b(today'?s|next|current|first)\b.*\btask\b|^(it|that|this)$", query):
        return pending[0]
    q = query.lower()
    scored = sorted(((SequenceMatcher(None, q, x.title.lower()).ratio() + (0.3 if any(w in x.title.lower() for w in q.split() if len(w) > 3) else 0), x)
                     for x in pending), key=lambda s: -s[0])
    return scored[0][1] if scored and scored[0][0] >= 0.45 else None


def validate(db: Session, workspace_id: str, p: Proposal) -> dict:
    """Return {valid, errors, summary, changes, consequential} for a proposal."""
    t = db.scalar(select(CareerTransition).where(CareerTransition.workspace_id == workspace_id, CareerTransition.is_active))
    errs: list[str] = []
    changes: list[dict] = []
    summary = ""
    prm = p.params
    if p.type not in ACTIONS:
        return {"valid": False, "errors": ["I could not match that to an action."], "summary": "", "changes": [], "consequential": False}
    if t is None and p.type not in ("add_application", "update_application_status"):
        return {"valid": False, "errors": ["Create or select a career goal first."], "summary": "", "changes": [], "consequential": False}
    if p.type == "set_weekly_hours":
        h = prm.get("hours")
        if not isinstance(h, (int, float)) or not 1 <= h <= 80:
            errs.append("Weekly hours must be between 1 and 80.")
        else:
            summary = f"Change weekly study time to {h:g} hours"
            changes.append({"field": "Weekly study hours", "from": t.weekly_hours, "to": h})  # type: ignore[union-attr]
    elif p.type == "set_deadline":
        try:
            d = date.fromisoformat(str(prm.get("deadline")))
            if d <= date.today():
                errs.append("The deadline must be in the future.")
            summary = f"Set your preparation deadline to {d.isoformat()}"
            changes.append({"field": "Deadline", "from": t.deadline.isoformat() if t.deadline else None, "to": d.isoformat()})  # type: ignore[union-attr]
        except ValueError:
            errs.append("I could not understand the date.")
    elif p.type == "set_budget":
        a = prm.get("amount")
        if not isinstance(a, (int, float)) or a < 0:
            errs.append("Budget must be zero or more.")
        else:
            cur = prm.get("currency") or t.budget_currency  # type: ignore[union-attr]
            summary = f"Set your learning budget to {a:g} {cur}" if a else "Use free resources only (budget 0)"
            changes.append({"field": "Budget", "from": f"{t.budget_amount} {t.budget_currency}", "to": f"{a:g} {cur}"})  # type: ignore[union-attr]
    elif p.type == "set_target_role":
        role = str(prm.get("role") or "").strip()
        if not 2 <= len(role) <= 160:
            errs.append("Please say the target role.")
        summary = f"Change your target role to \"{role}\""
        changes.append({"field": "Target role", "from": t.target_role, "to": role})  # type: ignore[union-attr]
    elif p.type == "complete_task":
        x = _find_task(db, t, str(prm.get("query", "")))  # type: ignore[arg-type]
        if x is None:
            errs.append("I could not find a matching open task in your current plan.")
        else:
            prm["task_id"] = x.id
            summary = f"Mark \"{x.title}\" as completed"
            changes.append({"field": "Task status", "item": x.title, "from": x.status, "to": "completed"})
    elif p.type == "add_application":
        if not prm.get("company") or not prm.get("role_title"):
            errs.append("Please say the company and the role.")
        summary = f"Add an application: {prm.get('role_title')} at {prm.get('company')} (status: {prm.get('status', 'applied')})"
        changes.append({"field": "New application", "to": f"{prm.get('role_title')} @ {prm.get('company')}"})
    elif p.type == "update_application_status":
        company = str(prm.get("company", "")).lower()
        apps = list(db.scalars(select(JobApplication).where(JobApplication.workspace_id == workspace_id)))
        match = [a for a in apps if company and (company in a.company.lower() or a.company.lower() in company)]
        if len(match) != 1:
            errs.append("No application for that company was found." if not match else "Several applications match; update it on the Applications page.")
        else:
            prm["application_id"] = match[0].id
            summary = f"Update {match[0].role_title} at {match[0].company} to \"{prm.get('status')}\""
            changes.append({"field": "Application status", "item": match[0].company, "from": match[0].status, "to": prm.get("status")})
    elif p.type == "start_topic_check":
        sid = prm.get("skill_id")
        if not sid:
            errs.append("I could not tell which skill to check.")
        summary = f"Start a short {skill_name(sid) if sid else ''} topic check"
    elif p.type == "regenerate_plan":
        summary = "Regenerate your learning plan (completed tasks are kept)"
    consequential = p.type not in ("start_topic_check",)
    return {"valid": not errs, "errors": errs, "summary": summary, "changes": changes, "consequential": consequential}
