import hashlib
from datetime import datetime

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.db import new_id
from app.deps import DB, Ctx, CtxDep
from app.errors import api_error
from app.models import ResumeVersion
from app.security.files import FileRejected, validate_resume_upload
from app.security.ratelimit import enforce
from app.services import resume as resume_svc
from app.services.audit import audit
from app.services.evidence import record_resume_evidence
from app.services.owned import get_owned
from app.services.storage import get_storage
from app.services.taxonomy import SKILL_BY_ID

router = APIRouter(tags=["resumes"])


class ResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int
    source: str
    filename: str | None
    extraction_method: str
    is_user_edited: bool
    parent_version_id: str | None
    created_at: datetime


class ResumeDetail(ResumeSummary):
    text_content: str
    extracted: dict


class PasteIn(BaseModel):
    text: str = Field(min_length=30, max_length=60000)


def _guard_versions(db, ctx: Ctx) -> int:
    n = db.scalar(select(func.count(ResumeVersion.id)).where(ResumeVersion.workspace_id == ctx.workspace_id)) or 0
    if ctx.is_guest and n >= get_settings().guest_max_resume_versions:
        raise api_error(403, "GUEST_LIMIT", "Guest workspaces keep a limited number of resume versions. Save your progress to keep more.")
    return n + 1


def _next_version(db, ctx: Ctx) -> int:
    _guard_versions(db, ctx)
    return (db.scalar(select(func.max(ResumeVersion.version_number)).where(ResumeVersion.workspace_id == ctx.workspace_id)) or 0) + 1


def _create(db, ctx: Ctx, *, text: str, source: str, filename: str | None = None, storage_key: str | None = None,
            parent: str | None = None, extracted: dict | None = None, method: str | None = None) -> ResumeVersion:
    text = resume_svc.clean_text(text)
    if extracted is None:
        ex, result = resume_svc.extract(db, workspace_id=ctx.workspace_id, is_guest=ctx.is_guest, text=text)
        extracted, method = ex.model_dump(), f"{result.method}:{result.provider}"
    rv = ResumeVersion(workspace_id=ctx.workspace_id, version_number=_next_version(db, ctx), source=source, filename=filename,
                       storage_key=storage_key, sha256=hashlib.sha256(text.encode()).hexdigest(), text_content=text,
                       extracted=extracted, extraction_method=method or "rules", is_user_edited=source == "edit",
                       parent_version_id=parent)
    db.add(rv)
    db.flush()
    record_resume_evidence(db, ctx.workspace_id, rv)
    audit(db, action="resume.created", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="resume", entity_id=rv.id,
          details={"source": source, "version": rv.version_number, "skills_found": len(extracted.get("skills", []))})
    db.commit()
    return rv


@router.post("/resumes/upload", response_model=ResumeDetail, status_code=201)
async def upload_resume(request: Request, db: DB, ctx: CtxDep, file: UploadFile = File(...)):
    enforce(request, "upload", get_settings().rate_limit_upload_per_minute, subject=ctx.workspace_id)
    _guard_versions(db, ctx)
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        vf = validate_resume_upload(file.filename, data)
        text = resume_svc.text_from_pdf(vf.data) if vf.kind == "pdf" else resume_svc.text_from_docx(vf.data)
    except FileRejected as e:
        audit(db, action="resume.rejected", workspace_id=ctx.workspace_id, actor=ctx.actor, details={"code": e.code})
        db.commit()
        raise api_error(400, e.code, e.message) from None
    key = f"{ctx.workspace_id}/{new_id()}.{vf.kind}"
    get_storage().put(key, vf.data, "application/pdf" if vf.kind == "pdf" else
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return _create(db, ctx, text=text, source=vf.kind, filename=vf.filename, storage_key=key)


@router.post("/resumes/text", response_model=ResumeDetail, status_code=201)
def paste_resume(body: PasteIn, request: Request, db: DB, ctx: CtxDep):
    enforce(request, "upload", get_settings().rate_limit_upload_per_minute, subject=ctx.workspace_id)
    return _create(db, ctx, text=body.text, source="paste")


@router.get("/resumes", response_model=list[ResumeSummary])
def list_resumes(db: DB, ctx: CtxDep):
    return db.scalars(select(ResumeVersion).where(ResumeVersion.workspace_id == ctx.workspace_id)
                      .order_by(ResumeVersion.version_number.desc())).all()


@router.get("/resumes/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: str, db: DB, ctx: CtxDep):
    return get_owned(db, ResumeVersion, resume_id, ctx.workspace_id, "Resume")


class EditedSkill(BaseModel):
    skill_id: str
    excerpt: str | None = Field(default=None, max_length=400)


class EditedExperience(BaseModel):
    title: str = Field(max_length=160)
    organization: str | None = Field(default=None, max_length=160)
    start: str | None = Field(default=None, max_length=20)
    end: str | None = Field(default=None, max_length=20)
    bullets: list[str] = Field(default_factory=list, max_length=30)


class ExtractionEdit(BaseModel):
    experiences: list[EditedExperience] = Field(max_length=30)
    education: list[str] = Field(default_factory=list, max_length=20)
    certifications: list[str] = Field(default_factory=list, max_length=20)
    skills: list[EditedSkill] = Field(max_length=80)
    total_years_experience: float | None = Field(default=None, ge=0, le=60)


@router.put("/resumes/{resume_id}/extracted", response_model=ResumeDetail, status_code=201)
def edit_extraction(resume_id: str, body: ExtractionEdit, db: DB, ctx: CtxDep):
    """Corrections create a new version, so the original extraction stays in history."""
    base = get_owned(db, ResumeVersion, resume_id, ctx.workspace_id, "Resume")
    unknown = [s.skill_id for s in body.skills if s.skill_id not in SKILL_BY_ID]
    if unknown:
        raise api_error(422, "UNKNOWN_SKILL", f"Unknown skills: {', '.join(unknown[:5])}")
    ex = dict(base.extracted)
    old = {s["skill_id"]: s for s in ex.get("skills", [])}
    skills = []
    for s in body.skills:
        if s.skill_id in old and not s.excerpt:
            skills.append(old[s.skill_id])
        else:
            excerpt = s.excerpt or "Added by you during review"
            ctxname = "experience" if s.excerpt and s.excerpt.lower() in base.text_content.lower() else "skills_list"
            skills.append({"skill_id": s.skill_id, "name": SKILL_BY_ID[s.skill_id]["name"],
                           "evidence": [{"excerpt": excerpt, "context": ctxname}]})
    ex.update(experiences=[e.model_dump() for e in body.experiences], education=body.education,
              certifications=body.certifications, skills=skills, total_years_experience=body.total_years_experience)
    return _create(db, ctx, text=base.text_content, source="edit", parent=base.id, extracted=ex, method="user_edit")


@router.delete("/resumes/{resume_id}", status_code=204)
def delete_resume(resume_id: str, db: DB, ctx: CtxDep):
    rv = get_owned(db, ResumeVersion, resume_id, ctx.workspace_id, "Resume")
    if rv.storage_key:
        get_storage().delete(rv.storage_key)
    db.delete(rv)
    audit(db, action="resume.deleted", workspace_id=ctx.workspace_id, actor=ctx.actor, entity_type="resume", entity_id=resume_id)
    db.commit()
