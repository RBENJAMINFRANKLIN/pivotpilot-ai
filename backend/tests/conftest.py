"""Test setup. Uses SQLite by default; set TEST_DATABASE_URL to run against PostgreSQL."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="pivotpilot-test-")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["STORAGE_LOCAL_DIR"] = f"{_tmp}/uploads"
os.environ["AI_PROVIDER"] = "rules"
os.environ["AUTH_MODE"] = "local"
os.environ["APP_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["CORS_ORIGINS"] = "http://testserver"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security.ratelimit import limiter  # noqa: E402
from app.seed.load import load_reference_data  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        load_reference_data(db)
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    limiter.reset()
    yield
    reference = {"skills", "skill_aliases", "skill_prerequisites", "learning_resources", "assessment_questions"}
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name not in reference:
                conn.execute(table.delete())
        conn.execute(text("DELETE FROM assessment_questions WHERE origin <> 'curated'"))
        conn.execute(text("DELETE FROM learning_resources WHERE source <> 'curated'"))
        conn.execute(text("UPDATE learning_resources SET verification_status = 'unverified', last_checked_at = NULL"))


class ApiClient(TestClient):
    """TestClient that sends the CSRF header like the real frontend."""

    def request(self, method, url, **kw):
        headers = dict(kw.pop("headers", None) or {})
        headers.setdefault("X-PivotPilot-Client", "web")
        return super().request(method, url, headers=headers, **kw)


@pytest.fixture
def client():
    with ApiClient(app) as c:
        yield c


@pytest.fixture
def guest(client):
    r = client.post("/api/v1/session/guest")
    assert r.status_code == 200, r.text
    return client


def new_client() -> ApiClient:
    return ApiClient(app)
