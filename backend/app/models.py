"""ORM models.

Tenancy: every user-owned row carries `workspace_id`. A workspace belongs to either a
guest session or an authenticated user. All queries filter on workspace_id, which also
makes guest-to-account migration a uniform, transactional re-assignment.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType, new_id, utcnow


def pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


def ws_fk() -> Mapped[str]:
    return mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


def created() -> Mapped[datetime]:
    return mapped_column(default=utcnow)


# --------------------------------------------------------------------------- identity


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = pk()
    auth_provider: Mapped[str] = mapped_column(String(20))  # local | supabase
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = created()
    last_login_at: Mapped[datetime | None]


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = pk()
    kind: Mapped[str] = mapped_column(String(10))  # guest | user
    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    guest_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None]
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created()
    last_seen_at: Mapped[datetime] = created()
    version: Mapped[int] = mapped_column(Integer, default=1)


class GuestMigration(Base):
    """One row per imported guest workspace. The unique constraint makes a second
    import of the same guest workspace impossible, even under concurrent requests."""

    __tablename__ = "guest_migrations"
    id: Mapped[str] = pk()
    guest_workspace_id: Mapped[str] = mapped_column(String(36), unique=True)
    target_workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"))
    rows_moved: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = created()


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(120))
    employment_status: Mapped[str | None] = mapped_column(String(40))
    current_role: Mapped[str | None] = mapped_column(String(160))
    current_industry: Mapped[str | None] = mapped_column(String(160))
    years_experience: Mapped[float | None] = mapped_column(Float)
    education: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(160))
    preferred_formats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    language: Mapped[str] = mapped_column(String(20), default="en")
    self_reported_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class CareerTransition(Base):
    __tablename__ = "career_transitions"
    __table_args__ = (
        # At most one active transition per workspace.
        Index(
            "uq_one_active_transition",
            "workspace_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    title: Mapped[str] = mapped_column(String(200))
    current_role: Mapped[str | None] = mapped_column(String(160))
    current_industry: Mapped[str | None] = mapped_column(String(160))
    employment_status: Mapped[str | None] = mapped_column(String(40))
    target_role: Mapped[str] = mapped_column(String(160))
    target_location: Mapped[str | None] = mapped_column(String(160))
    deadline: Mapped[date | None] = mapped_column(Date)
    weekly_hours: Mapped[float] = mapped_column(Float, default=6)
    study_days_per_week: Mapped[int] = mapped_column(Integer, default=5)
    budget_amount: Mapped[float | None] = mapped_column(Float)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD")
    learning_formats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    language: Mapped[str] = mapped_column(String(20), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


# --------------------------------------------------------------------------- resumes & jobs


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "version_number"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))  # pdf | docx | paste | edit
    filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    extracted: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(60))
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_version_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = created()


class JobDescription(Base):
    __tablename__ = "job_descriptions"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))  # url | paste | role_only
    source_url: Mapped[str | None] = mapped_column(String(2000))
    title: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    fetch_status: Mapped[str] = mapped_column(String(30), default="ok")
    analysis_method: Mapped[str | None] = mapped_column(String(60))
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created()
    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobRequirement.position"
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    job_description_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    skill_id: Mapped[str | None] = mapped_column(String(80), ForeignKey("skills.id"))
    label: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(30))
    importance: Mapped[str] = mapped_column(String(12))  # mandatory | preferred
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    min_years: Mapped[float | None] = mapped_column(Float)
    prerequisite_skill_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    job: Mapped[JobDescription] = relationship(back_populates="requirements")


class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    resume_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("resume_versions.id", ondelete="CASCADE"))
    job_description_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_descriptions.id", ondelete="CASCADE"))
    quality_score: Mapped[float] = mapped_column(Float)
    quality_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONType)
    fit_score: Mapped[float] = mapped_column(Float)
    fit_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONType)
    requirement_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    transferable_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    suggestions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    experience_alignment: Mapped[dict[str, Any]] = mapped_column(JSONType)
    scoring_version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = created()


# --------------------------------------------------------------------------- skills


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    learn_hours: Mapped[float] = mapped_column(Float, default=20)  # rough hours novice -> proficient


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(120), unique=True)


class SkillPrerequisite(Base):
    __tablename__ = "skill_prerequisites"
    skill_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    __table_args__ = (Index("ix_evidence_ws_skill", "workspace_id", "skill_id"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    skill_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id"))
    evidence_type: Mapped[str] = mapped_column(String(30))
    # self_reported | resume | quiz | practical | project | course_completion
    source_ref: Mapped[str | None] = mapped_column(String(120))
    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    excerpt: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = created()


class ProficiencyHistory(Base):
    __tablename__ = "proficiency_history"
    __table_args__ = (Index("ix_prof_ws_skill", "workspace_id", "skill_id", "created_at"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    skill_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id"))
    score: Mapped[float | None] = mapped_column(Float)  # None when evidence is insufficient
    level: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[str] = mapped_column(String(20))  # insufficient | low | medium | high
    questions_answered: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float | None] = mapped_column(Float)
    difficulty_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    methodology: Mapped[str] = mapped_column(String(40))
    source_ref: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = created()


# --------------------------------------------------------------------------- assessments


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (Index("ix_question_skill_diff", "skill_id", "difficulty"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspaces.id", ondelete="CASCADE"))
    skill_id: Mapped[str] = mapped_column(String(80), ForeignKey("skills.id"))
    topic: Mapped[str] = mapped_column(String(120))
    competency: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[int] = mapped_column(Integer)  # 1 easy, 2 medium, 3 hard
    qtype: Mapped[str] = mapped_column(String(20))
    # single | multi | code_output | short_answer | scenario | practical
    prompt: Mapped[str] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSONType, default=list)
    correct_answer: Mapped[Any] = mapped_column(JSONType)  # never sent to the client before answering
    explanation: Mapped[str] = mapped_column(Text)
    learning_objective: Mapped[str] = mapped_column(Text)
    validation_source: Mapped[str] = mapped_column(String(300))
    rubric: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    origin: Mapped[str] = mapped_column(String(20), default="curated")  # curated | generated
    validated: Mapped[bool] = mapped_column(Boolean, default=True)
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created()


class AssessmentBlueprint(Base):
    __tablename__ = "assessment_blueprints"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # diagnostic | topic_check
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    question_budget: Mapped[int] = mapped_column(Integer)
    uncovered: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    engine_version: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = created()


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    blueprint_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessment_blueprints.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress | completed | abandoned
    timed: Mapped[bool] = mapped_column(Boolean, default=False)
    seconds_per_question: Mapped[int | None] = mapped_column(Integer)
    current_question_id: Mapped[str | None] = mapped_column(String(80))
    current_served_at: Mapped[datetime | None]
    state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    started_at: Mapped[datetime] = created()
    completed_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1)


class AssessmentResponse(Base):
    __tablename__ = "assessment_responses"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(80), ForeignKey("assessment_questions.id"))
    skill_id: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[int] = mapped_column(Integer)
    served_at: Mapped[datetime]
    answered_at: Mapped[datetime | None]
    response: Mapped[Any] = mapped_column(JSONType, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)  # 0..1, None when not evaluable
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_exposure: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    evaluation_method: Mapped[str | None] = mapped_column(String(30))


# --------------------------------------------------------------------------- resources


class LearningResource(Base):
    __tablename__ = "learning_resources"
    id: Mapped[str] = pk()
    title: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(120))
    canonical_url: Mapped[str] = mapped_column(String(2000), unique=True)
    resource_type: Mapped[str] = mapped_column(String(30))  # course | video | docs | book | tutorial | practice
    description: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str]] = mapped_column(JSONType, default=list)
    prerequisites: Mapped[list[str]] = mapped_column(JSONType, default=list)
    level: Mapped[str] = mapped_column(String(20), default="beginner")
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    duration_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_type: Mapped[str] = mapped_column(String(20), default="unknown")  # free | freemium | paid | subscription | unknown
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(3))
    language: Mapped[str] = mapped_column(String(20), default="en")
    formats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    source: Mapped[str] = mapped_column(String(20))  # curated | youtube | search
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")  # verified | stale | unverified | broken
    last_checked_at: Mapped[datetime | None]
    last_check_detail: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created()


class ResourceRecommendation(Base):
    __tablename__ = "resource_recommendations"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_resources.id", ondelete="CASCADE"))
    skill_id: Mapped[str] = mapped_column(String(80))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    ranking_method: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = created()


# --------------------------------------------------------------------------- learning plans


class LearningPlan(Base):
    __tablename__ = "learning_plans"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), unique=True
    )
    current_version_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused
    created_at: Mapped[datetime] = created()


class LearningPlanVersion(Base):
    __tablename__ = "learning_plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version_number"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_plans.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # provisional | final
    reason: Mapped[str] = mapped_column(String(300))
    based_on_attempt_id: Mapped[str | None] = mapped_column(String(36))
    start_date: Mapped[date] = mapped_column(Date)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType)
    weeks: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    feasibility: Mapped[dict[str, Any]] = mapped_column(JSONType)
    generation_method: Mapped[str] = mapped_column(String(40))
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created()


class PlanTask(Base):
    __tablename__ = "plan_tasks"
    __table_args__ = (Index("ix_task_version_week", "plan_version_id", "week_number", "day_number"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    plan_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_plan_versions.id", ondelete="CASCADE"))
    week_number: Mapped[int] = mapped_column(Integer)
    day_number: Mapped[int] = mapped_column(Integer)
    scheduled_date: Mapped[date] = mapped_column(Date)
    skill_id: Mapped[str | None] = mapped_column(String(80))
    task_type: Mapped[str] = mapped_column(String(20))  # lesson | exercise | quiz | project | revision | milestone
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("learning_resources.id", ondelete="SET NULL"))
    project_id: Mapped[str | None] = mapped_column(String(36))
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | in_progress | completed | paused | skipped
    completion_criteria: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    carried_from_task_id: Mapped[str | None] = mapped_column(String(36))
    completed_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1)


class TaskCompletion(Base):
    __tablename__ = "task_completions"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("plan_tasks.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(20))  # completed | reopened | paused | resumed | rescheduled | skipped
    minutes_spent: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()


# --------------------------------------------------------------------------- projects, interviews, applications


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    problem_statement: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(JSONType)
    milestones: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    deliverables: Mapped[list[str]] = mapped_column(JSONType)
    rubric: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    resume_evidence: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested | in_progress | completed | dropped
    repo_url: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created()


class ProjectEvidence(Base):
    __tablename__ = "project_evidence"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # link | note | rubric_self_assessment | milestone
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2000))
    rubric_scores: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = created()


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(160))
    question_ids: Mapped[list[str]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    overall_score: Mapped[float | None] = mapped_column(Float)
    rubric_version: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = created()
    completed_at: Mapped[datetime | None]


class InterviewEvaluation(Base):
    __tablename__ = "interview_evaluations"
    __table_args__ = (UniqueConstraint("interview_id", "question_id"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(80))
    question_text: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20))
    response_text: Mapped[str] = mapped_column(Text)
    criterion_scores: Mapped[dict[str, Any]] = mapped_column(JSONType)
    overall: Mapped[float] = mapped_column(Float)
    feedback: Mapped[dict[str, Any]] = mapped_column(JSONType)
    method: Mapped[str] = mapped_column(String(30))
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = created()


class JobApplication(Base):
    __tablename__ = "job_applications"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    transition_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("career_transitions.id", ondelete="SET NULL"), index=True)
    company: Mapped[str] = mapped_column(String(200))
    role_title: Mapped[str] = mapped_column(String(200))
    role_category: Mapped[str] = mapped_column(String(80))
    company_size: Mapped[str] = mapped_column(String(20), default="unknown")
    source: Mapped[str] = mapped_column(String(60), default="other")
    url: Mapped[str | None] = mapped_column(String(2000))
    resume_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("resume_versions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="saved")
    applied_at: Mapped[date | None] = mapped_column(Date)
    interview_dates: Mapped[list[str]] = mapped_column(JSONType, default=list)
    outcome: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str] = ws_fk()
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_applications.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = created()


# --------------------------------------------------------------------------- audit & usage


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = pk()
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True)  # kept after workspace deletion
    user_id: Mapped[str | None] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(10))  # guest | user | system
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created()


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_ws_time", "workspace_id", "created_at"),)
    id: Mapped[str] = pk()
    workspace_id: Mapped[str | None] = mapped_column(String(36))
    feature: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = created()


# Tables whose rows move when a guest workspace is imported into an account (order matters
# only for readability; all updates run in one transaction).
OWNED_TABLES = [
    CareerTransition, ResumeVersion, JobDescription, JobRequirement, ResumeAnalysis, SkillEvidence,
    ProficiencyHistory, AssessmentQuestion, AssessmentBlueprint, AssessmentAttempt, AssessmentResponse,
    ResourceRecommendation, LearningPlan, LearningPlanVersion, PlanTask, TaskCompletion, Project,
    ProjectEvidence, Interview, InterviewEvaluation, JobApplication, ApplicationEvent,
]
