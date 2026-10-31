from datetime import date, timedelta

import httpx

from app.db import SessionLocal
from app.models import LearningResource
from app.services.resources import verify_resource
from tests.helpers import full_intake
from tests.test_assessment import right, run, wrong


def make_plan(client, t, **body):
    r = client.post(f"/api/v1/transitions/{t['id']}/plan", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_plan_respects_weekly_hours(guest):
    for hours in (2, 5, 12):
        t = full_intake(guest, weekly_hours=hours, title=f"h{hours}")
        plan = make_plan(guest, t)
        per_week: dict[int, int] = {}
        for task in plan["tasks"]:
            per_week[task["week"]] = per_week.get(task["week"], 0) + task["minutes"]
        assert per_week and max(per_week.values()) <= hours * 60
        for w in plan["weeks"]:
            assert w["planned_minutes"] <= w["capacity_minutes"] == hours * 60


def test_plan_is_provisional_before_assessment_and_final_after(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    assert plan["status"] == "provisional" and "Provisional" in plan["summary"]["status_note"]
    view, _ = run(guest, t, right)
    assert view["results"]["plan_revision"]["reasons"][0].startswith("diagnostic results")
    plan2 = guest.get(f"/api/v1/transitions/{t['id']}/plan").json()
    assert plan2["status"] == "final" and plan2["version"] == 2
    assert [v["version"] for v in plan2["versions"]] == [2, 1]


def test_quiz_materially_changes_plan(guest):
    t1 = full_intake(guest, title="strong")
    run(guest, t1, right)
    strong = make_plan(guest, t1)
    t2 = full_intake(guest, title="weak", role="Data Analyst")
    guest.post(f"/api/v1/transitions/{t2['id']}/activate")
    run(guest, t2, wrong)
    weak = make_plan(guest, t2)
    assert weak["summary"]["total_hours"] > strong["summary"]["total_hours"]


def test_prerequisites_ordered_first(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    order = [s["skill_id"] for s in plan["summary"]["skills"]]
    if "pandas" in order and "python" in order:
        assert order.index("python") < order.index("pandas")
    first_task = {}
    for x in plan["tasks"]:
        if x["skill_id"]:
            first_task.setdefault(x["skill_id"], (x["week"], x["day"]))
    if "pandas" in first_task and "python" in first_task:
        assert first_task["python"] <= first_task["pandas"]


def test_every_task_explains_relevance(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    lessons = [x for x in plan["tasks"] if x["type"] == "lesson"]
    assert lessons and all("for this role" in x["rationale"] for x in lessons)
    assert all(x["resource"] and x["resource"]["url"].startswith("https://") for x in lessons)
    types = {x["type"] for x in plan["tasks"]}
    assert {"lesson", "exercise", "quiz", "milestone", "project", "revision"} <= types


def test_unrealistic_deadline_reports_conflict_and_alternatives(guest):
    t = full_intake(guest, weekly_hours=2, deadline=(date.today() + timedelta(days=60)).isoformat())
    plan = make_plan(guest, t)
    f = plan["feasibility"]
    assert f["conflict"] is True and f["weeks_needed"] > f["weeks_available"]
    kinds = {a["type"] for a in f["alternatives"]}
    assert {"extend_deadline", "increase_hours", "reduce_scope"} <= kinds
    mandatory = make_plan(guest, t, scope="mandatory_only")
    assert mandatory["summary"]["total_hours"] < plan["summary"]["total_hours"]
    assert all(s["importance"] == "mandatory" for s in mandatory["summary"]["skills"])


def test_revision_preserves_completed_work(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    done = [x for x in plan["tasks"] if x["type"] == "lesson"][:2]
    for x in done:
        r = guest.patch(f"/api/v1/tasks/{x['id']}", json={"status": "completed", "minutes_spent": 45})
        assert r.status_code == 200 and r.json()["status"] == "completed"
    plan2 = make_plan(guest, t, reason="I changed my hours")
    carried = [x for x in plan2["tasks"] if x["carried_over"]]
    assert {x["title"] for x in carried} == {x["title"] for x in done}
    assert all(x["status"] == "completed" and x["week"] == 0 for x in carried)
    # old version's tasks can no longer be changed
    assert guest.patch(f"/api/v1/tasks/{done[0]['id']}", json={"status": "pending"}).status_code == 409


def test_reschedule_respects_capacity(guest):
    t = full_intake(guest, weekly_hours=3)
    plan = make_plan(guest, t)
    week1 = [x for x in plan["tasks"] if x["week"] == 1]
    later = next(x for x in plan["tasks"] if x["week"] == 2)
    r = guest.patch(f"/api/v1/tasks/{later['id']}", json={"scheduled_date": week1[0]["date"]})
    used = sum(x["minutes"] for x in week1)
    if used + later["minutes"] > 180:
        assert r.status_code == 409 and r.json()["detail"]["code"] == "CAPACITY_EXCEEDED"
    else:
        assert r.status_code == 200


def test_course_completion_does_not_change_assessed_proficiency(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    before = guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()
    sql_lessons = [x for x in plan["tasks"] if x["skill_id"] == "sql" and x["type"] == "lesson"]
    for x in sql_lessons:
        guest.patch(f"/api/v1/tasks/{x['id']}", json={"status": "completed"})
    after = guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()
    s_before = next(i for i in before["items"] if i["skill_id"] == "sql")
    s_after = next(i for i in after["items"] if i["skill_id"] == "sql")
    assert s_before["current"] == s_after["current"] and s_after["basis"] == "provisional"


def test_topic_check_after_course_updates_proficiency_and_revises_plan(guest):
    t = full_intake(guest)
    run(guest, t, wrong)  # diagnostic: weak everywhere, plan becomes final when generated
    plan = make_plan(guest, t)
    sql_before = next(s for s in plan["summary"]["skills"] if s["skill_id"] == "sql")
    view, served = run(guest, t, right, kind="topic_check", skill_id="sql")
    assert view["results"]["skills"]["sql"]["score"] >= sql_before["target"]
    rev = view["results"]["plan_revision"]
    assert rev and any("SQL reached its target" in r for r in rev["reasons"])
    plan2 = guest.get(f"/api/v1/transitions/{t['id']}/plan").json()
    assert "sql" not in {s["skill_id"] for s in plan2["summary"]["skills"]}
    gaps = guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()
    assert next(i for i in gaps["items"] if i["skill_id"] == "sql")["gap"] == 0


def test_resource_recommendations_are_catalogue_backed_with_rationale(guest):
    t = full_intake(guest, budget_amount=0)
    make_plan(guest, t)
    data = guest.get(f"/api/v1/transitions/{t['id']}/resources").json()
    assert data["groups"]
    with SessionLocal() as db:
        known = {r.canonical_url for r in db.query(LearningResource)}
    for g in data["groups"]:
        assert any(i["cost_type"] == "free" for i in g["items"])  # zero budget -> free option
        for i in g["items"]:
            assert i["url"] in known
            assert i["rationale"] and i["verification_status"] in ("verified", "unverified", "stale")
            assert i["duration_minutes"] is None or i["duration_verified"]
            assert i["price"] is None  # never invented
    assert all(not d["configured"] for d in data["discovery"])


def test_resource_verification_states():
    def handler(request):
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(404)
        return httpx.Response(404 if "gone" in str(request.url) else 200, headers={"content-type": "text/html"}, text="<title>x</title>")

    ok = LearningResource(title="a", provider="p", canonical_url="https://example.org/ok", resource_type="docs", source="curated")
    gone = LearningResource(title="b", provider="p", canonical_url="https://example.org/gone", resource_type="docs", source="curated")
    tr = httpx.MockTransport(handler)
    assert verify_resource(ok, transport=tr) == "verified" and ok.last_checked_at
    assert verify_resource(gone, transport=tr) == "broken"


def test_projects_suggested_with_rubric_and_evidence(guest):
    t = full_intake(guest)
    projects = guest.get(f"/api/v1/transitions/{t['id']}/projects").json()
    assert projects and projects[0]["rubric"] and projects[0]["milestones"]
    assert "[" in projects[0]["resume_evidence"]  # placeholders, never invented results
    p = projects[0]
    r = guest.post(f"/api/v1/projects/{p['id']}/evidence", json={"kind": "rubric_self_assessment",
                                                                 "rubric_scores": {"problem": 4, "method": 3, "quality": 3, "communication": 4}})
    assert r.status_code == 201 and r.json()["evidence"][0]["score"] > 70
    readiness = guest.get(f"/api/v1/transitions/{t['id']}/readiness").json()
    assert "project_evidence" in readiness["components"]
