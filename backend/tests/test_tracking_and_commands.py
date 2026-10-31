from datetime import date

from app.services.commands import parse_date, parse_rules
from tests.conftest import new_client
from tests.helpers import full_intake
from tests.test_plan import make_plan

STAR_ANSWER = ("When I was teaching Year 11, our pass rate in algebra was 68%. My goal was to raise it within two years. "
               "I analysed termly assessment data in Excel because I wanted to find the topics where students struggled, "
               "then I designed short weekly practice quizzes and met colleagues to share results. As a result the pass rate "
               "rose to 81%, and the department adopted the quiz approach. However, it took time to get buy-in, so next time I "
               "would involve colleagues earlier.")


def test_mock_interview_rubric_and_no_invented_experience(guest):
    t = full_intake(guest)
    iv = guest.post(f"/api/v1/transitions/{t['id']}/interviews").json()
    assert len(iv["questions"]) == 5 and {c["id"] for c in iv["rubric"]} == {"relevance", "structure", "evidence", "depth", "communication"}
    types = {q["type"] for q in iv["questions"]}
    assert {"behavioral", "technical"} <= types
    q0 = iv["questions"][0]
    good = guest.post(f"/api/v1/interviews/{iv['id']}/answers", json={"question_id": q0["id"], "response_text": STAR_ANSWER}).json()
    q1 = iv["questions"][1]
    weak = guest.post(f"/api/v1/interviews/{iv['id']}/answers", json={"question_id": q1["id"], "response_text": "I am good at it."}).json()
    g, w = good["questions"][0], weak["questions"][1]
    assert g["overall"] > w["overall"] and g["method"] == "heuristic_rubric"
    assert w["feedback"]["improvements"]
    assert all("[" in line for line in g["feedback"]["outline"] if ":" in line)  # placeholders only
    assert guest.post(f"/api/v1/interviews/{iv['id']}/answers", json={"question_id": q0["id"], "response_text": "again"}).status_code == 409
    for q in iv["questions"][2:]:
        res = guest.post(f"/api/v1/interviews/{iv['id']}/answers", json={"question_id": q["id"], "response_text": STAR_ANSWER}).json()
    assert res["status"] == "completed" and res["overall_score"] is not None
    readiness = guest.get(f"/api/v1/transitions/{t['id']}/readiness").json()
    assert "interview_performance" in readiness["components"]


def test_application_tracking_history_and_cautious_analytics(guest):
    full_intake(guest)
    a = guest.post("/api/v1/applications", json={"company": "Acme", "role_title": "Data Analyst", "status": "applied"}).json()
    assert a["status"] == "applied" and [h["to"] for h in a["history"]] == ["saved", "applied"]
    a = guest.patch(f"/api/v1/applications/{a['id']}", json={"status": "interview", "interview_date": "2030-01-10", "version": a["version"]}).json()
    assert a["interview_dates"] == ["2030-01-10"] and a["history"][-1]["to"] == "interview"
    stale = guest.patch(f"/api/v1/applications/{a['id']}", json={"status": "offer", "version": 1})
    assert stale.status_code == 409
    an = guest.get("/api/v1/applications/analytics").json()
    row = an["by_role_category"][0]
    assert row["sent"] == 1 and row["enough_data"] is False
    assert "Not enough data" in an["insights"][0]


def test_analytics_learns_which_roles_respond(guest):
    for i in range(5):
        guest.post("/api/v1/applications", json={"company": f"A{i}", "role_title": "x", "role_category": "reporting analyst", "status": "screening"})
        guest.post("/api/v1/applications", json={"company": f"B{i}", "role_title": "y", "role_category": "data scientist", "status": "no_response"})
    an = guest.get("/api/v1/applications/analytics").json()
    assert "reporting analyst" in an["insights"][0] and "5/5" in an["insights"][0]


def test_application_isolation(guest):
    a = guest.post("/api/v1/applications", json={"company": "Acme", "role_title": "DA"}).json()
    other = new_client()
    other.post("/api/v1/session/guest")
    assert other.patch(f"/api/v1/applications/{a['id']}", json={"status": "offer"}).status_code == 404
    assert other.get("/api/v1/applications").json() == []


# ----------------------------------------------------------------------------- dictated commands


def test_rule_parser_understands_dictated_phrases():
    cases = {
        "Um, I can study about 8 hours a week now.": ("set_weekly_hours", {"hours": 8.0}),
        "I have ten hours per week": ("set_weekly_hours", {"hours": 10.0}),
        "Change my deadline to 2030-06-30": ("set_deadline", {"deadline": "2030-06-30"}),
        "I only want free courses only": ("set_budget", {"amount": 0, "currency": None}),
        "My budget is $200": ("set_budget", {"amount": 200.0, "currency": "USD"}),
        "I want to become a product manager": ("set_target_role", {"role": "Product Manager"}),
        "Quiz me on SQL": ("start_topic_check", {"skill_id": "sql"}),
        "Please regenerate my plan": ("regenerate_plan", {}),
        "I applied for the junior data analyst role at Acme Retail": ("add_application", {"role_title": "Junior Data Analyst", "company": "Acme Retail", "status": "applied"}),
        "Acme rejected me": ("update_application_status", {"company": "Acme", "status": "rejected"}),
        "I got an interview with Contoso!": ("update_application_status", {"company": "Contoso", "status": "interview"}),
        "I finished today's task": ("complete_task", {"query": "today's task"}),
    }
    for text, (typ, params) in cases.items():
        p = parse_rules(text)
        assert p is not None, text
        assert p.type == typ and p.params == params, (text, p)
    assert parse_rules("hello there") is None


def test_parse_dates():
    today = date(2026, 1, 15)
    assert parse_date("deadline is March 15 2027", today) == date(2027, 3, 15)
    assert parse_date("ready by the end of june", today) == date(2026, 6, 30)
    assert parse_date("in 3 months", today) == date(2026, 4, 15)
    assert parse_date("by 1 february", today) == date(2026, 2, 1)


def test_command_interpret_confirm_execute_flow(guest):
    t = full_intake(guest)
    r = guest.post("/api/v1/commands/interpret", json={"text": "I can study 9 hours a week"}).json()
    assert r["understood"] and r["valid"] and r["requires_confirmation"]
    assert r["changes"][0] == {"field": "Weekly study hours", "from": 6.0, "to": 9.0}
    # Not executed until confirmed:
    assert guest.post("/api/v1/commands/execute", json={**r["action"], "confirmed": False}).status_code == 409
    assert guest.get(f"/api/v1/transitions/{t['id']}").json()["weekly_hours"] == 6.0
    done = guest.post("/api/v1/commands/execute", json={**r["action"], "confirmed": True}).json()
    assert done["ok"] and done["result"]["transition"]["weekly_hours"] == 9.0
    assert guest.get(f"/api/v1/transitions/{t['id']}").json()["weekly_hours"] == 9.0


def test_command_complete_task_and_invalid_values(guest):
    t = full_intake(guest)
    plan = make_plan(guest, t)
    first = next(x for x in plan["tasks"] if x["week"] == 1)
    r = guest.post("/api/v1/commands/interpret", json={"text": "I finished today's task"}).json()
    assert r["valid"] and r["action"]["params"]["task_id"] == first["id"]
    guest.post("/api/v1/commands/execute", json={**r["action"], "confirmed": True})
    tasks = guest.get(f"/api/v1/transitions/{t['id']}/plan").json()["tasks"]
    assert next(x for x in tasks if x["id"] == first["id"])["status"] == "completed"
    bad = guest.post("/api/v1/commands/interpret", json={"text": "I can study 200 hours a week"}).json()
    assert bad["valid"] is False and "between 1 and 80" in bad["errors"][0]
    # tampered execute payload is re-validated server-side
    r = guest.post("/api/v1/commands/execute", json={"type": "set_weekly_hours", "params": {"hours": 500}, "confirmed": True})
    assert r.status_code == 422


def test_command_add_application_and_status(guest):
    full_intake(guest)
    r = guest.post("/api/v1/commands/interpret", json={"text": "I applied for a reporting analyst role at Contoso"}).json()
    guest.post("/api/v1/commands/execute", json={**r["action"], "confirmed": True})
    r = guest.post("/api/v1/commands/interpret", json={"text": "I have a screening call with Contoso"}).json()
    assert r["valid"], r
    guest.post("/api/v1/commands/execute", json={**r["action"], "confirmed": True})
    apps = guest.get("/api/v1/applications").json()
    assert apps[0]["company"] == "Contoso" and apps[0]["status"] == "screening"


def test_dashboard_and_next_actions(guest):
    d = guest.get("/api/v1/dashboard").json()
    assert d["transition"] is None and d["next_actions"][0]["id"] == "create_goal"
    t = full_intake(guest)
    d = guest.get("/api/v1/dashboard").json()
    assert d["transition"]["id"] == t["id"] and d["next_actions"][0]["id"] == "take_assessment"
    assert d["scores"]["resume_quality"] and d["gaps"]["status"] == "provisional"


def test_demo_workspace(client):
    r = client.post("/api/v1/demo/start")
    assert r.status_code == 200, r.text
    d = client.get("/api/v1/dashboard").json()
    assert d["is_demo"] and d["plan"]["status"] == "final" and d["plan"]["progress_percent"] > 0
    assert d["proficiency"] and d["applications"]["total"] == 3
    excel = next(p for p in d["proficiency"] if p["skill_id"] == "excel")
    sql = next(p for p in d["proficiency"] if p["skill_id"] == "sql")
    assert excel["latest"]["score"] > sql["latest"]["score"]
