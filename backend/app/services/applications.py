"""Manual application tracking and cautious response analytics."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationEvent, JobApplication

STATUSES = ["saved", "applied", "screening", "interview", "offer", "rejected", "withdrawn", "no_response"]
RESPONDED = {"screening", "interview", "offer", "rejected"}  # the employer replied in some way
POSITIVE = {"screening", "interview", "offer"}
MIN_SAMPLE = 5


def set_status(db: Session, app: JobApplication, status: str, note: str | None = None) -> None:
    if status == app.status:
        return
    db.add(ApplicationEvent(workspace_id=app.workspace_id, application_id=app.id, from_status=app.status, to_status=status, note=note))
    app.status = status


def _ever(db: Session, app: JobApplication) -> set[str]:
    return {e.to_status for e in db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id))} | {app.status}


def analytics(db: Session, workspace_id: str) -> dict:
    apps = list(db.scalars(select(JobApplication).where(JobApplication.workspace_id == workspace_id)))
    sent = [a for a in apps if a.status != "saved"]
    pipeline = {s: sum(1 for a in apps if a.status == s) for s in STATUSES}

    def group(attr: str) -> list[dict]:
        out = {}
        for a in sent:
            g = out.setdefault(getattr(a, attr) or "unknown", {"key": getattr(a, attr) or "unknown", "sent": 0, "responses": 0, "positive": 0})
            hist = _ever(db, a)
            g["sent"] += 1
            g["responses"] += 1 if hist & RESPONDED else 0
            g["positive"] += 1 if hist & POSITIVE else 0
        rows = []
        for g in out.values():
            g["response_rate"] = round(g["responses"] / g["sent"], 2)
            g["positive_rate"] = round(g["positive"] / g["sent"], 2)
            g["enough_data"] = g["sent"] >= MIN_SAMPLE
            rows.append(g)
        return sorted(rows, key=lambda r: (-r["sent"], r["key"]))

    by_category = group("role_category")
    insights = []
    solid = [g for g in by_category if g["enough_data"]]
    if len(solid) >= 2:
        best, worst = max(solid, key=lambda g: g["positive_rate"]), min(solid, key=lambda g: g["positive_rate"])
        if best["positive_rate"] - worst["positive_rate"] >= 0.2:
            insights.append(f"\"{best['key']}\" roles led to screens or interviews more often ({best['positive']}/{best['sent']}) than "
                            f"\"{worst['key']}\" roles ({worst['positive']}/{worst['sent']}). Small samples; treat this as a hint, not a rule.")
    if not insights:
        insights.append(f"Not enough data yet: patterns are shown once a role type has at least {MIN_SAMPLE} sent applications.")
    return {"total": len(apps), "sent": len(sent), "pipeline": pipeline, "by_role_category": by_category,
            "by_company_size": group("company_size"), "by_source": group("source"), "insights": insights, "min_sample": MIN_SAMPLE}
