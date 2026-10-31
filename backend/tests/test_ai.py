"""AI provider abstraction: grounding, validation, fallback and usage logging, using a fake client."""

import pytest
from sqlalchemy import select

from app.ai import llm
from app.config import get_settings
from app.db import SessionLocal
from app.models import AIUsageLog
from app.seed.demo_content import DEMO_JOB, DEMO_RESUME
from tests.helpers import setup_transition


class FakeClient:
    def __init__(self, responder):
        self.responder = responder

    def complete(self, system, user, schema, max_tokens):
        out = self.responder(schema, user)
        if isinstance(out, Exception):
            raise out
        return schema.model_validate(out), llm.Usage(100, 50, "fake-model")


@pytest.fixture
def ai(monkeypatch):
    def use(responder, tasks="*"):
        monkeypatch.setattr(get_settings(), "ai_provider", "anthropic")
        llm.set_client_factory("anthropic", lambda: FakeClient(responder))

    yield use
    llm.set_client_factory("anthropic", llm.AnthropicClient)


def test_ai_resume_extraction_drops_ungrounded_items(guest, ai):
    def responder(schema, user):
        return {"experiences": [
            {"title": "Mathematics Teacher", "organization": "Lakeside High School", "start": "Aug 2017", "end": "Present",
             "quote": "Mathematics Teacher, Lakeside High School  Aug 2017 - Present"},
            {"title": "Senior Data Scientist", "organization": "Google", "start": "2010", "end": "2015", "quote": "Senior Data Scientist at Google"}],
            "education": ["BSc Mathematics, State University, 2015", "PhD Physics, MIT"], "certifications": []}

    ai(responder)
    body = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).json()
    titles = [e["title"] for e in body["extracted"]["experiences"]]
    assert titles == ["Mathematics Teacher"]  # the invented role is rejected
    assert body["extracted"]["education"] == ["BSc Mathematics, State University, 2015"]
    assert body["extraction_method"] == "llm:anthropic"


def test_ai_job_analysis_requires_real_excerpts(guest, ai):
    def responder(schema, user):
        return {"requirements": [
            {"label": "SQL", "category": "skill", "importance": "mandatory", "source_excerpt": "Strong SQL skills are required"},
            {"label": "Kubernetes", "category": "tool", "importance": "mandatory", "source_excerpt": "Must know Kubernetes"},
            {"label": "Looker", "category": "tool", "importance": "preferred", "source_excerpt": "Experience with Tableau or Power BI is preferred"}]}

    ai(responder)
    t = setup_transition(guest)
    job = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "paste", "text": DEMO_JOB}).json()["job"]
    labels = {r["label"] for r in job["requirements"]}
    assert "Kubernetes" not in labels and "Docker & containers" not in labels  # fabricated requirement dropped
    assert job["analysis_method"] == "llm:anthropic"


def test_llm_failure_falls_back_to_rules_and_is_logged(guest, ai):
    ai(lambda schema, user: llm.AIUnavailable("AI_UNREACHABLE", "down"))
    body = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME})
    assert body.status_code == 201
    assert body.json()["extraction_method"] == "rules_fallback:rules"
    with SessionLocal() as db:
        logs = db.scalars(select(AIUsageLog).where(AIUsageLog.feature == "resume_extraction")).all()
        assert any(not log.success and log.error_code == "AI_UNREACHABLE" for log in logs)
        assert any(log.provider == "rules" and log.success for log in logs)


def test_invalid_ai_output_is_retried_then_rejected(guest, ai):
    calls = []

    def responder(schema, user):
        calls.append(1)
        return {"not": "valid"}

    ai(responder)
    body = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME})
    assert body.status_code == 201 and body.json()["extraction_method"].startswith("rules_fallback")
    assert len(calls) == 2  # one corrective retry, then fall back


def test_ai_unavailable_for_generation_without_rules_returns_clear_error(guest):
    from app.services.commands import LLMProposal

    with SessionLocal() as db, pytest.raises(llm.AIUnavailable) as e:
        llm.run_task(db, workspace_id=None, is_guest=True, task="question_generation", prompt_version="x", system="s", user="u",
                     schema=LLMProposal, rules=None)
    assert "not available" in e.value.message


def test_ai_daily_budget_falls_back(guest, ai, monkeypatch):
    ai(lambda schema, user: {"experiences": [], "education": [], "certifications": []})
    monkeypatch.setattr(get_settings(), "guest_daily_ai_calls", 1)
    first = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).json()
    second = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).json()
    assert first["extraction_method"] == "llm:anthropic"
    assert second["extraction_method"] == "rules_fallback:rules"


def test_saved_data_available_when_ai_down(guest, ai):
    t = setup_transition(guest)
    guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME})
    ai(lambda schema, user: llm.AIUnavailable("AI_UNREACHABLE", "down"))
    assert guest.get("/api/v1/resumes").status_code == 200
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "paste", "text": DEMO_JOB})
    assert r.json()["status"] == "ok"  # deterministic analysis still works
