"""Resume text extraction and structured analysis.

Rule-based extraction always runs and is the grounding reference. When an AI provider is
configured it may add structure (titles, organisations), but every AI-provided item must
quote text that literally appears in the resume, or it is dropped."""

import io
import re
from datetime import date

from pydantic import BaseModel, Field

from app.ai.llm import AIResult, run_task, untrusted
from app.config import get_settings
from app.security.files import FileRejected
from app.services.taxonomy import SKILL_BY_ID, excerpt_in, find_skills, split_units

PROMPT_VERSION = "resume-extract-v1"

SECTION_WORDS = {
    "summary": ["summary", "profile", "about me", "professional summary", "objective"],
    "experience": ["experience", "work experience", "employment", "work history", "professional experience", "career history"],
    "education": ["education", "qualifications", "academic background"],
    "skills": ["skills", "technical skills", "core skills", "competencies", "key skills", "tools"],
    "projects": ["projects", "portfolio", "selected projects"],
    "certifications": ["certifications", "certificates", "licenses", "licences", "training"],
}
ACTION_VERBS = {
    "achieved", "analysed", "analyzed", "built", "created", "designed", "developed", "delivered", "drove", "established",
    "implemented", "improved", "increased", "introduced", "launched", "led", "managed", "mentored", "organised",
    "organized", "planned", "reduced", "redesigned", "resolved", "streamlined", "taught", "trained", "coordinated",
    "automated", "collaborated", "presented", "produced", "supported", "tracked", "wrote", "facilitated", "coached",
}
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE = rf"(?:{MONTHS}\s+)?(?:19|20)\d{{2}}|\d{{1,2}}/(?:19|20)\d{{2}}"
RANGE = re.compile(rf"({DATE})\s*(?:-|–|—|to)\s*({DATE}|present|current|now|today)", re.IGNORECASE)
NUMBER = re.compile(r"\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
LINK = re.compile(r"(?:linkedin\.com|github\.com|https?://)", re.IGNORECASE)


# ----------------------------------------------------------------------------- file parsing


def text_from_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise FileRejected("ENCRYPTED_FILE", "Password-protected PDFs cannot be read. Remove the password and try again.")
        if len(reader.pages) > get_settings().max_pdf_pages:
            raise FileRejected("TOO_MANY_PAGES", f"Resumes longer than {get_settings().max_pdf_pages} pages are not accepted.")
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except FileRejected:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as e:
        raise FileRejected("MALFORMED_FILE", "The PDF could not be read. It may be damaged.") from e
    if len(text.strip()) < 50:
        raise FileRejected("NO_TEXT", "No readable text was found. Scanned images are not supported; paste the text instead.")
    return text


def text_from_docx(data: bytes) -> str:
    import docx

    try:
        d = docx.Document(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001 - python-docx raises many types on bad input
        raise FileRejected("MALFORMED_FILE", "The document could not be read. It may be damaged.") from e
    lines = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            lines.append(" | ".join(c.text.strip() for c in row.cells if c.text.strip()))
    text = "\n".join(lines)
    if len(text.strip()) < 50:
        raise FileRejected("NO_TEXT", "No readable text was found in the document.")
    return text


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:60000]


# ----------------------------------------------------------------------------- rule-based extraction


class SkillEvidenceItem(BaseModel):
    excerpt: str
    context: str  # experience | skills_list | summary | projects | education | other


class ExtractedSkill(BaseModel):
    skill_id: str
    name: str
    evidence: list[SkillEvidenceItem]


class Experience(BaseModel):
    title: str
    organization: str | None = None
    start: str | None = None
    end: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ResumeExtraction(BaseModel):
    sections: list[str]
    contact: dict[str, bool]
    experiences: list[Experience]
    education: list[str]
    certifications: list[str]
    skills: list[ExtractedSkill]
    total_years_experience: float | None
    word_count: int
    bullet_count: int
    quantified_bullets: int
    action_verb_bullets: int


def _heading(line: str) -> str | None:
    s = line.strip().strip(":").lower()
    if len(s) > 40:
        return None
    for sec, words in SECTION_WORDS.items():
        if s in words:
            return sec
    return None


def _parse_date(s: str, end: bool) -> date | None:
    s = s.strip().lower()
    if s in ("present", "current", "now", "today"):
        return date.today()
    m = re.match(r"(\d{1,2})/(\d{4})", s)
    if m:
        return date(int(m.group(2)), max(1, min(12, int(m.group(1)))), 1)
    year = re.search(r"(19|20)\d{2}", s)
    if not year:
        return None
    month = 12 if end else 1
    for i, name in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
        if s.startswith(name):
            month = i + 1
    return date(int(year.group(0)), month, 1)


def _merged_years(ranges: list[tuple[date, date]]) -> float:
    ranges = sorted(r for r in ranges if r[1] >= r[0])
    total, cur = 0, None
    for s, e in ranges:
        if cur and s <= cur[1]:
            cur = (cur[0], max(cur[1], e))
        else:
            if cur:
                total += (cur[1] - cur[0]).days
            cur = (s, e)
    if cur:
        total += (cur[1] - cur[0]).days
    return round(total / 365.25, 1)


def extract_rules(text: str) -> ResumeExtraction:
    raw_lines = [ln.rstrip() for ln in text.splitlines()]
    section = "other"
    sections: set[str] = set()
    line_section: list[str] = []
    for ln in raw_lines:
        h = _heading(ln)
        if h:
            section = h
            sections.add(h)
        line_section.append(section)

    experiences: list[Experience] = []
    ranges: list[tuple[date, date]] = []
    education: list[str] = []
    certs: list[str] = []
    bullets: list[str] = []
    current: Experience | None = None
    for i, ln in enumerate(raw_lines):
        s = ln.strip()
        if not s or _heading(s):
            continue
        sec = line_section[i]
        m = RANGE.search(s)
        is_bullet = bool(re.match(r"^\s*[•\-*·▪●–]\s+", ln))
        if m and sec in ("experience", "other", "projects"):
            title = RANGE.sub("", s).strip(" |,–—-()")
            if not title and i > 0:
                title = raw_lines[i - 1].strip()
            org = None
            for sep in (" at ", " | ", ", ", " – ", " - "):
                if sep in title:
                    title, org = (p.strip() for p in title.split(sep, 1))
                    break
            current = Experience(title=title[:160] or "Role", organization=(org or None) and org[:160], start=m.group(1), end=m.group(2))
            experiences.append(current)
            sd, ed = _parse_date(m.group(1), False), _parse_date(m.group(2), True)
            if sd and ed:
                ranges.append((sd, ed))
            continue
        if is_bullet or (current and sec == "experience" and len(s) > 30):
            b = re.sub(r"^\s*[•\-*·▪●–]\s+", "", ln).strip()
            bullets.append(b)
            if current and sec in ("experience", "other", "projects"):
                current.bullets.append(b[:400])
            continue
        if sec == "education":
            education.append(s[:200])
        elif sec == "certifications":
            certs.append(s[:200])

    units = split_units(text)
    unit_section = []
    for u in units:  # map each excerpt back to the section it came from
        idx = next((i for i, ln in enumerate(raw_lines) if u[:60] in ln), None)
        unit_section.append(line_section[idx] if idx is not None else "other")
    skills: list[ExtractedSkill] = []
    for skill_id, matches in find_skills(text).items():
        ev = []
        for m in matches[:4]:
            ctx = unit_section[m.line_index] if m.line_index < len(unit_section) else "other"
            ctx = "skills_list" if ctx == "skills" else ctx
            if ctx == "other" and any(m.excerpt in b for b in bullets):
                ctx = "experience"
            ev.append(SkillEvidenceItem(excerpt=m.excerpt, context=ctx))
        skills.append(ExtractedSkill(skill_id=skill_id, name=SKILL_BY_ID[skill_id]["name"], evidence=ev))

    return ResumeExtraction(
        sections=sorted(sections),
        contact={"email": bool(EMAIL.search(text)), "phone": bool(PHONE.search(text)), "link": bool(LINK.search(text))},
        experiences=experiences,
        education=education[:10],
        certifications=certs[:10],
        skills=sorted(skills, key=lambda s: s.skill_id),
        total_years_experience=_merged_years(ranges) if ranges else None,
        word_count=len(text.split()),
        bullet_count=len(bullets),
        quantified_bullets=sum(1 for b in bullets if NUMBER.search(b)),
        action_verb_bullets=sum(1 for b in bullets if b.split(" ", 1)[0].lower().strip(",.") in ACTION_VERBS),
    )


# ----------------------------------------------------------------------------- AI-assisted extraction


class LLMExperience(BaseModel):
    title: str
    organization: str | None = None
    start: str | None = None
    end: str | None = None
    quote: str = Field(description="A line copied exactly from the resume that names this role")


class LLMResume(BaseModel):
    experiences: list[LLMExperience]
    education: list[str]
    certifications: list[str]


SYSTEM = (
    "You extract structured facts from a resume for a career-planning tool. Extract only what the resume states. "
    "For each role, copy one line from the resume exactly into `quote`. Do not infer skills, dates or employers that "
    "are not written. Use the dates as written (e.g. 'Sep 2019', 'Present')."
)


def extract(db, *, workspace_id: str, is_guest: bool, text: str) -> tuple[ResumeExtraction, AIResult]:
    base = extract_rules(text)

    def rules() -> LLMResume:
        return LLMResume(
            experiences=[LLMExperience(title=e.title, organization=e.organization, start=e.start, end=e.end, quote=e.title) for e in base.experiences],
            education=base.education, certifications=base.certifications)

    def grounded(out: LLMResume) -> LLMResume:
        out.experiences = [e for e in out.experiences if excerpt_in(e.quote, text) and excerpt_in(e.title, text)]
        out.education = [e for e in out.education if excerpt_in(e, text)]
        out.certifications = [c for c in out.certifications if excerpt_in(c, text)]
        return out

    result = run_task(db, workspace_id=workspace_id, is_guest=is_guest, task="resume_extraction", prompt_version=PROMPT_VERSION,
                      system=SYSTEM, user=untrusted("resume", text), schema=LLMResume, rules=rules, validate=grounded,
                      contains_resume=True)
    if result.method == "llm" and result.data.experiences:
        bullets_by_title = {e.title: e.bullets for e in base.experiences}
        base.experiences = [Experience(title=e.title, organization=e.organization, start=e.start, end=e.end,
                                       bullets=bullets_by_title.get(e.title, [])) for e in result.data.experiences]
        base.education = result.data.education or base.education
        base.certifications = result.data.certifications or base.certifications
    return base, result
