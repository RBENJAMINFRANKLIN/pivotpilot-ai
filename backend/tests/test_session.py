from tests.conftest import new_client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["database"] == "ok"


def test_no_session_is_401(client):
    r = client.get("/api/v1/transitions")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "NO_SESSION"


def test_guest_session_persists_and_discloses_retention(guest):
    s1 = guest.get("/api/v1/session").json()
    assert s1["kind"] == "guest"
    assert "days" in s1["retention_notice"]
    # A second call (e.g. after refresh) reuses the same workspace via the cookie.
    s2 = guest.post("/api/v1/session/guest").json()
    assert s2["workspace_id"] == s1["workspace_id"]


def test_guest_cookie_is_httponly(client):
    r = client.post("/api/v1/session/guest")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_csrf_header_required_for_cookie_requests(client):
    from fastapi.testclient import TestClient

    from app.main import app

    raw = TestClient(app)
    r = raw.post("/api/v1/session/guest")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "CSRF_HEADER_MISSING"


def test_register_login_and_cross_session_persistence(client):
    r = client.post("/api/v1/auth/register", json={"email": "Ana@Example.com", "password": "correct horse battery", "display_name": "Ana"})
    assert r.status_code == 200, r.text
    client.post("/api/v1/transitions", json={"title": "Into data", "target_role": "Data Analyst", "weekly_hours": 6})
    # A different device: new client, log in, see the same data.
    other = new_client()
    r = other.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "correct horse battery"})
    assert r.status_code == 200
    items = other.get("/api/v1/transitions").json()
    assert [t["title"] for t in items] == ["Into data"]


def test_bearer_token_works_without_cookie(client):
    token = client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "long enough password"}).json()["access_token"]
    other = new_client()
    r = other.get("/api/v1/session", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["kind"] == "user"


def test_bad_login(client):
    client.post("/api/v1/auth/register", json={"email": "c@example.com", "password": "long enough password"})
    r = new_client().post("/api/v1/auth/login", json={"email": "c@example.com", "password": "wrong password!!"})
    assert r.status_code == 401


def test_login_rate_limited(client):
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "nope nope nope"})
    r = client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "nope nope nope"})
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}


def test_guest_to_account_migration_is_atomic_and_not_duplicated(guest):
    guest.post("/api/v1/transitions", json={"title": "Guest goal", "target_role": "Data Analyst", "weekly_hours": 5})
    guest.post("/api/v1/resumes/text", json={"text": "Teacher\nUsed Excel to track grades.\nEducation: BA"})
    guest_ws = guest.get("/api/v1/session").json()["workspace_id"]

    r = guest.post("/api/v1/auth/register", json={"email": "g@example.com", "password": "long enough password"})
    assert r.status_code == 200
    r = guest.post("/api/v1/auth/migrate-guest")
    assert r.status_code == 200, r.text
    moved = r.json()["rows_moved"]
    assert moved["career_transitions"] == 1 and moved["resume_versions"] == 1

    s = guest.get("/api/v1/session").json()
    assert s["kind"] == "user" and s["workspace_id"] != guest_ws
    assert [t["title"] for t in guest.get("/api/v1/transitions").json()] == ["Guest goal"]

    # The guest cookie is cleared, so a second import has nothing to import.
    r = guest.post("/api/v1/auth/migrate-guest")
    assert r.status_code == 404


def test_migration_replay_with_stolen_old_cookie_is_rejected(guest):
    guest.post("/api/v1/transitions", json={"title": "G", "target_role": "Data Analyst", "weekly_hours": 5})
    old_cookie = guest.cookies.get("pp_guest")
    guest.post("/api/v1/auth/register", json={"email": "h@example.com", "password": "long enough password"})
    assert guest.post("/api/v1/auth/migrate-guest").status_code == 200
    guest.cookies.set("pp_guest", old_cookie)
    r = guest.post("/api/v1/auth/migrate-guest")
    assert r.status_code == 404  # the guest workspace no longer exists
    assert len(guest.get("/api/v1/transitions").json()) == 1


def test_migration_keeps_single_active_goal(guest):
    guest.post("/api/v1/transitions", json={"title": "Guest goal", "target_role": "Data Analyst", "weekly_hours": 5})
    acct = new_client()
    acct.post("/api/v1/auth/register", json={"email": "k@example.com", "password": "long enough password"})
    acct.post("/api/v1/transitions", json={"title": "Account goal", "target_role": "Product Manager", "weekly_hours": 5})
    login = guest.post("/api/v1/auth/login", json={"email": "k@example.com", "password": "long enough password"})
    assert login.status_code == 200
    assert guest.post("/api/v1/auth/migrate-guest").status_code == 200
    items = guest.get("/api/v1/transitions").json()
    assert sorted(t["title"] for t in items) == ["Account goal", "Guest goal"]
    assert [t["title"] for t in items if t["is_active"]] == ["Account goal"]


def test_data_isolation_between_workspaces(guest):
    t = guest.post("/api/v1/transitions", json={"title": "Mine", "target_role": "Data Analyst", "weekly_hours": 5}).json()
    intruder = new_client()
    intruder.post("/api/v1/session/guest")
    assert intruder.get(f"/api/v1/transitions/{t['id']}").status_code == 404
    assert intruder.patch(f"/api/v1/transitions/{t['id']}", json={"title": "hacked"}).status_code == 404
    assert intruder.get("/api/v1/transitions").json() == []


def test_delete_workspace(guest):
    guest.post("/api/v1/transitions", json={"title": "X", "target_role": "Data Analyst", "weekly_hours": 5})
    assert guest.delete("/api/v1/workspace").status_code == 400
    assert guest.delete("/api/v1/workspace?confirm=DELETE").status_code == 200
    assert guest.get("/api/v1/transitions").status_code == 401
