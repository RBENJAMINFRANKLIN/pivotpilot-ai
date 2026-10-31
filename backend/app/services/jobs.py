"""Job description intake and competency-map extraction."""

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.ai.llm import AIResult, run_task, untrusted
from app.security.netfetch import FetchBlocked, safe_get
from app.seed.skills import role_template
from app.services.taxonomy import SKILL_BY_ID, excerpt_in, find_skills, prerequisites, split_units

PROMPT_VERSION = "job-analysis-v1"

# Sites whose terms prohibit automated access to job pages: ask for pasted text instead.
NO_FETCH_DOMAINS = ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com", "monster.com")
EXPIRED_MARKERS = ("no longer accepting applications", "this job has expired", "position has been filled",
                   "job is no longer available", "this posting has closed", "job not found")
CATEGORY_FOR = {"technical": "skill", "tool": "tool", "domain": "domain", "professional": "professional"}


@dataclass
class FetchedJob:
    status: str  # ok | blocked | expired | insufficient | error
    message: str
    text: str = ""
    title: str | None = None
    company: str | None = None
    url: str | None = None


def _jsonld_job(soup: BeautifulSoup) -> dict | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def html_to_job(html: str) -> tuple[str, str | None, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    posting = _jsonld_job(soup)
    if posting and posting.get("description"):
        desc = BeautifulSoup(str(posting["description"]), "html.parser").get_text("\n")
        org = posting.get("hiringOrganization")
        company = org.get("name") if isinstance(org, dict) else None
        return desc, posting.get("title"), company
    for t in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        t.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    title = soup.find("h1")
    return main.get_text("\n"), title.get_text(strip=True) if title else None, None


def fetch_job(url: str, transport=None) -> FetchedJob:
    host = (urlparse(url).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in NO_FETCH_DOMAINS):
        return FetchedJob("blocked", f"{host} does not allow automated reading of job pages. Please paste the job description text.", url=url)
    try:
        res = safe_get(url, transport=transport)
    except FetchBlocked as e:
        return FetchedJob("blocked", f"{e.message} Please paste the job description text instead.", url=url)
    except Exception:  # noqa: BLE001 - network failures of any kind fall back to pasted text
        return FetchedJob("error", "The page could not be loaded. Please paste the job description text instead.", url=url)
    if res.status_code in (404, 410):
        return FetchedJob("expired", "This job posting appears to have been removed. Please paste the text if you saved it.", url=url)
    if res.status_code >= 400:
        return FetchedJob("blocked", f"The website refused the request (HTTP {res.status_code}). Please paste the job description text.", url=url)
    text, title, company = html_to_job(res.text) if "html" in res.content_type or "<" in res.text[:200] else (res.text, None, None)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    low = text.lower()
    if any(m in low for m in EXPIRED_MARKERS):
        return FetchedJob("expired", "This job posting says it is closed or expired. Please paste the text if you still want to use it.", url=url)
    if len(text) < 200:
        return FetchedJob("insufficient", "Not enough job description text was found on that page. Please paste the text instead.", url=url)
    return FetchedJob("ok", "Job description loaded.", text=text[:40000], title=title, company=company, url=res.url)


# ----------------------------------------------------------------------------- competency map


class Requirement(BaseModel):
    label: str
    category: str  # skill | tool | domain | professional | experience | education | certification | responsibility
    importance: str  # mandatory | preferred
    skill_id: str | None = None
    source_excerpt: str | None = None
    confidence: float = 0.5
    min_years: float | None = None
    prerequisite_skill_ids: list[str] = Field(default_factory=list)


@dataclass
class CompetencyMap:
    requirements: list[Requirement] = field(default_factory=list)
    source: str = "job_description"  # job_description | role_template


MANDATORY_HEAD = re.compile(r"(requirement|qualification|must have|what you('| wi)ll need|what we('| a)re looking for|you have|about you|skills)", re.I)
PREFERRED_HEAD = re.compile(r"(nice to have|preferred|bonus|desirable|pluses|good to have|ideally)", re.I)
RESP_HEAD = re.compile(r"(responsibilit|what you('| wi)ll do|the role|day to day|duties|your impact)", re.I)
MUST = re.compile(r"\b(required|must|essential|minimum|need to have|proficien(t|cy) (in|with))\b", re.I)
NICE = re.compile(r"\b(preferred|nice to have|a plus|bonus|ideally|desirable|familiarity)\b", re.I)
YEARS = re.compile(r"(\d{1,2})\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)", re.I)
DEGREE = re.compile(r"\b(bachelor|master|degree|phd|b\.?s\.?c?|m\.?s\.?c?)\b", re.I)
CERT = re.compile(r"\b(certification|certified|certificate)\b", re.I)


def _unit_sections(text: str) -> list[tuple[str, str]]:
    out, section = [], "unknown"
    for unit in split_units(text):
        short = len(unit) < 60 and not find_skills(unit)  # a heading names a section, not a skill
        if short and PREFERRED_HEAD.search(unit):
            section = "preferred"
            continue
        if short and RESP_HEAD.search(unit):
            section = "responsibilities"
            continue
        if short and MANDATORY_HEAD.search(unit):
            section = "requirements"
            continue
        out.append((section, unit))
    return out


def analyze_rules(text: str) -> CompetencyMap:
    reqs: dict[str, Requirement] = {}
    extra: list[Requirement] = []
    responsibilities = 0
    for section, unit in _unit_sections(text):
        if NICE.search(unit) or section == "preferred":
            importance, conf = "preferred", 0.75 if NICE.search(unit) else 0.65
        elif MUST.search(unit) or section == "requirements":
            importance, conf = "mandatory", 0.8 if MUST.search(unit) else 0.7
        elif section == "responsibilities":
            importance, conf = "mandatory", 0.55
        else:
            importance, conf = "preferred", 0.45
        for skill_id in find_skills(unit):
            sk = SKILL_BY_ID[skill_id]
            prev = reqs.get(skill_id)
            if prev:
                # Explicit statements (requirement/preferred sections, 0.65+) beat inferences from
                # responsibilities or unlabelled text; between equals, mandatory wins.
                prev_explicit, explicit = prev.confidence >= 0.65, conf >= 0.65
                if prev_explicit != explicit:
                    if prev_explicit:
                        continue
                elif prev.importance == "mandatory" or importance == "preferred":
                    continue
            reqs[skill_id] = Requirement(label=sk["name"], category=CATEGORY_FOR[sk["category"]], importance=importance,
                                         skill_id=skill_id, source_excerpt=unit[:400], confidence=conf,
                                         prerequisite_skill_ids=prerequisites(skill_id))
        y = YEARS.search(unit)
        if y and "experience" in unit.lower() and not any(r.category == "experience" for r in extra):
            extra.append(Requirement(label=f"{y.group(1)}+ years of relevant experience", category="experience",
                                     importance="preferred" if NICE.search(unit) else "mandatory",
                                     source_excerpt=unit[:400], confidence=0.8, min_years=float(y.group(1))))
        if DEGREE.search(unit) and not any(r.category == "education" for r in extra):
            extra.append(Requirement(label="Degree requirement", category="education",
                                     importance="preferred" if NICE.search(unit) or re.search(r"or equivalent", unit, re.I) else "mandatory",
                                     source_excerpt=unit[:400], confidence=0.7))
        if CERT.search(unit) and not any(r.category == "certification" for r in extra):
            extra.append(Requirement(label="Certification mentioned", category="certification", importance="preferred",
                                     source_excerpt=unit[:400], confidence=0.6))
        if section == "responsibilities" and responsibilities < 8 and len(unit) > 25:
            extra.append(Requirement(label=unit[:200], category="responsibility", importance="mandatory",
                                     source_excerpt=unit[:400], confidence=0.9))
            responsibilities += 1
    order = {"mandatory": 0, "preferred": 1}
    skills = sorted(reqs.values(), key=lambda r: (order[r.importance], r.label))
    return CompetencyMap(requirements=skills + extra)


def role_template_map(target_role: str) -> CompetencyMap | None:
    tpl = role_template(target_role)
    if not tpl:
        return None
    reqs = []
    for importance in ("mandatory", "preferred"):
        for sid in tpl[importance]:
            sk = SKILL_BY_ID[sid]
            reqs.append(Requirement(label=sk["name"], category=CATEGORY_FOR[sk["category"]], importance=importance, skill_id=sid,
                                    source_excerpt=None, confidence=0.4, prerequisite_skill_ids=prerequisites(sid)))
    return CompetencyMap(requirements=reqs, source="role_template")


class LLMRequirement(BaseModel):
    label: str
    category: str = Field(description="skill | tool | domain | professional | experience | education | certification | responsibility")
    importance: str = Field(description="mandatory | preferred")
    source_excerpt: str = Field(description="Exact sentence copied from the job description")
    min_years: float | None = None


class LLMJob(BaseModel):
    title: str | None = None
    company: str | None = None
    requirements: list[LLMRequirement]


SYSTEM = (
    "You turn a job description into a competency map for a career-planning tool. List every requirement the posting "
    "states: skills, tools, domain knowledge, professional competencies, experience, education, certifications and key "
    "responsibilities. Mark a requirement mandatory only if the posting presents it as required; otherwise preferred. "
    "For each, copy the supporting sentence exactly into source_excerpt. Never add requirements the posting does not state."
)
VALID_CATS = {"skill", "tool", "domain", "professional", "experience", "education", "certification", "responsibility"}


def analyze(db, *, workspace_id: str, is_guest: bool, text: str) -> tuple[CompetencyMap, AIResult | None]:
    base = analyze_rules(text)

    def rules() -> LLMJob:
        return LLMJob(requirements=[])

    def grounded(out: LLMJob) -> LLMJob:
        out.requirements = [r for r in out.requirements if r.category in VALID_CATS and r.importance in ("mandatory", "preferred")
                            and excerpt_in(r.source_excerpt, text)]
        return out

    result = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="job_analysis", prompt_version=PROMPT_VERSION,
                      system=SYSTEM, user=untrusted("job_description", text), schema=LLMJob, rules=rules, validate=grounded)
    if result.method != "llm" or not result.data.requirements:
        return base, result
    merged = {r.skill_id: r for r in base.requirements if r.skill_id}
    others = [r for r in base.requirements if not r.skill_id]
    for lr in result.data.requirements:
        matches = find_skills(lr.label) or find_skills(lr.source_excerpt)
        sid = next(iter(matches), None) if lr.category in ("skill", "tool", "domain", "professional") else None
        if sid:
            prev = merged.get(sid)
            if prev is None or (prev.importance == "preferred" and lr.importance == "mandatory"):
                merged[sid] = Requirement(label=SKILL_BY_ID[sid]["name"], category=CATEGORY_FOR[SKILL_BY_ID[sid]["category"]],
                                          importance=lr.importance, skill_id=sid, source_excerpt=lr.source_excerpt[:400],
                                          confidence=0.8, prerequisite_skill_ids=prerequisites(sid))
        elif lr.category in ("skill", "tool", "domain", "professional"):
            # Requirement the taxonomy does not know: keep it, unscored, for the user to review.
            others.append(Requirement(label=lr.label[:200], category=lr.category, importance=lr.importance,
                                      source_excerpt=lr.source_excerpt[:400], confidence=0.6))
    order = {"mandatory": 0, "preferred": 1}
    return CompetencyMap(requirements=sorted(merged.values(), key=lambda r: (order[r.importance], r.label)) + others), result
