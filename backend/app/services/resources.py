"""Hybrid resource discovery.

A. Curated catalogue (seed/resources.py): reviewed canonical URLs, always available.
B. Live discovery: PLACEHOLDER providers with a fixed interface. They return nothing until
   configured (YouTube Data API / Google Programmable Search keys). See docs/FUTURE.md.

Ranking is deterministic (ranking-v1): no course details are ever generated; an AI
provider, when configured later, may only re-order already-retrieved resources.
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import as_utc, utcnow
from app.models import CareerTransition, LearningResource, ResourceRecommendation
from app.security.netfetch import FetchBlocked, safe_get
from app.services.taxonomy import skill_name

RANKING_VERSION = "ranking-v1"


# ----------------------------------------------------------------------------- live discovery (placeholder)


@dataclass
class DiscoveredResource:
    title: str
    provider: str
    url: str
    skills: list[str]
    resource_type: str
    source: str


class DiscoveryProvider:
    name = "base"

    def configured(self) -> bool:
        return False

    def search(self, skill_id: str, query: str) -> list[DiscoveredResource]:
        return []


class YouTubeDiscovery(DiscoveryProvider):
    """PLACEHOLDER: implement with the YouTube Data API v3 `search.list` + `videos.list`
    (documented, key-based). Needs YOUTUBE_API_KEY."""

    name = "youtube"

    def configured(self) -> bool:
        return bool(get_settings().youtube_api_key)


class WebSearchDiscovery(DiscoveryProvider):
    """PLACEHOLDER: implement with the Google Programmable Search JSON API, restricted to
    reputable provider domains. Needs GOOGLE_CSE_API_KEY and GOOGLE_CSE_ENGINE_ID."""

    name = "web_search"

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.google_cse_api_key and s.google_cse_engine_id)


DISCOVERY_PROVIDERS: list[DiscoveryProvider] = [YouTubeDiscovery(), WebSearchDiscovery()]


def discovery_status() -> list[dict]:
    return [{"provider": p.name, "configured": p.configured(),
             "note": None if p.configured() else "Not configured in this local demo; curated catalogue is used."}
            for p in DISCOVERY_PROVIDERS]


# ----------------------------------------------------------------------------- verification


def effective_status(r: LearningResource) -> str:
    if r.verification_status == "verified" and r.last_checked_at and \
            utcnow() - as_utc(r.last_checked_at) > timedelta(days=get_settings().resource_stale_after_days):  # type: ignore[operator]
        return "stale"
    return r.verification_status


def verify_resource(r: LearningResource, transport=None) -> str:
    """Link check of a catalogue URL (never a user-supplied URL)."""
    try:
        res = safe_get(r.canonical_url, transport=transport)
        if res.status_code < 400:
            r.verification_status, r.last_check_detail = "verified", f"HTTP {res.status_code}"
        elif res.status_code in (404, 410):
            r.verification_status, r.last_check_detail = "broken", f"HTTP {res.status_code}"
        else:
            r.verification_status, r.last_check_detail = "unverified", f"HTTP {res.status_code}"
    except FetchBlocked as e:
        r.verification_status, r.last_check_detail = "unverified", e.code
    except Exception as e:  # noqa: BLE001 - network errors leave the resource unverified
        r.verification_status, r.last_check_detail = "unverified", type(e).__name__
    r.last_checked_at = utcnow()
    return r.verification_status


# ----------------------------------------------------------------------------- ranking


def _score(r: LearningResource, skill_id: str, gap: dict, t: CareerTransition) -> tuple[float, list[str]]:
    why = []
    primary = r.skills[:1] == [skill_id]
    match = 1.0 if primary else 0.7
    why.append(f"Covers {skill_name(skill_id)}" + ("" if primary else " as part of a broader course"))
    beginner = gap["current"] < 45
    level = 1.0 if (r.level == "beginner") == beginner else 0.6
    why.append(f"{r.level.capitalize()} level suits your current {gap['basis']} level ({gap['current']:.0f}/100)" if level == 1.0
               else f"{r.level.capitalize()} level (may be {'advanced' if beginner else 'basic'} for you)")
    if r.cost_type == "free":
        cost = 1.0
        why.append("Free")
    elif t.budget_amount == 0:
        cost = 0.3
        why.append("Paid or subscription; your budget is zero, so a free option is listed too")
    else:
        cost = 0.85 if r.cost_type in ("paid", "subscription") else 0.7
        why.append({"subscription": "Subscription-based", "paid": "Paid"}.get(r.cost_type, "Cost not verified"))
    fmt = 1.0 if not t.learning_formats or set(r.formats) & set(t.learning_formats) else 0.75
    if t.learning_formats and fmt == 1.0:
        why.append(f"Matches your preferred format ({', '.join(sorted(set(r.formats) & set(t.learning_formats)))})")
    status = effective_status(r)
    ver = {"verified": 1.0, "unverified": 0.85, "stale": 0.8}.get(status, 0.0)
    lang = 1.0 if r.language == t.language else 0.5
    score = 0.35 * match + 0.15 * level + 0.15 * cost + 0.1 * fmt + 0.15 * ver + 0.1 * lang
    return round(score, 3), why


def recommend(db: Session, t: CareerTransition, gaps: list[dict], per_skill: int = 3) -> list[ResourceRecommendation]:
    db.execute(delete(ResourceRecommendation).where(ResourceRecommendation.transition_id == t.id))
    catalogue = [r for r in db.scalars(select(LearningResource)) if effective_status(r) != "broken"]
    recs = []
    for g in gaps:
        if g["gap"] <= 0:
            continue
        cands = [r for r in catalogue if g["skill_id"] in r.skills]
        scored = sorted(((*_score(r, g["skill_id"], g, t), r) for r in cands), key=lambda x: (-x[0], x[2].title))
        picks = scored[:per_skill]
        if picks and all(p[2].cost_type != "free" for p in picks):  # always offer a free alternative when one exists
            free = next((s for s in scored if s[2].cost_type == "free"), None)
            if free:
                picks = picks[: per_skill - 1] + [free]
        for rank, (score, why, r) in enumerate(picks, start=1):
            importance = f"a {g['importance']} requirement" + (f" (\"{g['job_excerpt'][:90]}\")" if g.get("job_excerpt") else "")
            rec = ResourceRecommendation(workspace_id=t.workspace_id, transition_id=t.id, resource_id=r.id, skill_id=g["skill_id"],
                                         rank=rank, score=score, ranking_method=RANKING_VERSION,
                                         rationale=f"{skill_name(g['skill_id'])} is {importance}. " + "; ".join(why) + ".")
            db.add(rec)
            recs.append(rec)
    db.flush()
    return recs


def resource_out(r: LearningResource) -> dict:
    return {"id": r.id, "title": r.title, "provider": r.provider, "url": r.canonical_url, "type": r.resource_type,
            "skills": r.skills, "prerequisites": r.prerequisites, "level": r.level,
            "duration_minutes": r.duration_minutes if r.duration_verified else None, "duration_verified": r.duration_verified,
            "cost_type": r.cost_type, "price": r.price, "currency": r.currency, "language": r.language, "formats": r.formats,
            "source": r.source, "verification_status": effective_status(r),
            "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None, "description": r.description}
