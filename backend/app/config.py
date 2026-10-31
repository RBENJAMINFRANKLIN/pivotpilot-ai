"""Environment-based configuration. Every setting can be overridden with an env var."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AIProviderName = Literal["rules", "anthropic", "openai_compatible"]
AI_TASKS = (
    "resume_extraction",
    "job_analysis",
    "question_generation",
    "answer_evaluation",
    "plan_generation",
    "resource_ranking",
    "interview_feedback",
    "command_parsing",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_secret: str = Field(default="dev-insecure-secret-change-me", min_length=16)
    database_url: str = "sqlite:///./pivotpilot.db"
    cors_origins: str = "http://localhost:5173"
    public_base_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Sessions & auth
    auth_mode: Literal["local", "supabase"] = "local"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""
    access_token_ttl_minutes: int = 60 * 24 * 7
    cookie_secure: bool = False
    guest_retention_days: int = 14
    guest_max_transitions: int = 3
    guest_max_resume_versions: int = 5
    guest_daily_ai_calls: int = 40
    user_daily_ai_calls: int = 300

    # Uploads & storage
    storage_backend: Literal["local", "supabase"] = "local"
    storage_local_dir: str = "./data/uploads"
    supabase_storage_bucket: str = "resumes"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pdf_pages: int = 15
    max_docx_uncompressed_bytes: int = 30 * 1024 * 1024

    # AI providers
    ai_provider: AIProviderName = "rules"
    ai_provider_overrides: str = ""  # e.g. "question_generation=anthropic,resume_extraction=openai_compatible"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    openai_compatible_base_url: str = "http://localhost:11434/v1"
    openai_compatible_api_key: str = ""
    openai_compatible_model: str = "llama3.1"
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    ai_max_output_tokens: int = 8000
    ai_max_input_chars: int = 60000
    ai_send_resume_to_hosted: bool = True

    # Resource discovery
    youtube_api_key: str = ""
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""
    resource_stale_after_days: int = 30
    outbound_fetch_timeout_seconds: float = 10.0
    outbound_max_bytes: int = 2 * 1024 * 1024
    outbound_user_agent: str = "PivotPilotBot/1.0 (+https://github.com/RBENJAMINFRANKLIN/pivotpilot-ai)"

    # Rate limits (requests per minute)
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 10
    rate_limit_upload_per_minute: int = 6
    rate_limit_ai_per_minute: int = 20
    rate_limit_guest_create_per_hour: int = 20

    demo_mode_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Render/Supabase hand out postgres:// URLs; SQLAlchemy + psycopg3 wants postgresql+psycopg://
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def provider_for(self, task: str) -> AIProviderName:
        for pair in self.ai_provider_overrides.split(","):
            if "=" in pair:
                k, v = (s.strip() for s in pair.split("=", 1))
                if k == task and v in ("rules", "anthropic", "openai_compatible"):
                    return v  # type: ignore[return-value]
        return self.ai_provider

    def validate_for_production(self) -> list[str]:
        problems = []
        if self.environment == "production":
            if self.app_secret.startswith("dev-insecure"):
                problems.append("APP_SECRET must be set to a long random value in production")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true in production (HTTPS)")
            if self.database_url.startswith("sqlite"):
                problems.append("DATABASE_URL should point to PostgreSQL in production")
            if self.auth_mode == "supabase" and not (self.supabase_url and (self.supabase_jwt_secret or self.supabase_url)):
                problems.append("Supabase auth needs SUPABASE_URL and SUPABASE_JWT_SECRET")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
