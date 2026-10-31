import json
from datetime import timedelta

from app.db import SessionLocal, utcnow
from app.models import AssessmentAttempt
from app.seed.questions import QUESTIONS
from tests.helpers import full_intake

KEY = {q["id"]: q for q in QUESTIONS}


def right(q):
    a = KEY[q["id"]]["correct_answer"]
    return a["accepted"][0] if isinstance(a, dict) else a


def wrong(q):
    a = KEY[q["id"]]["correct_answer"]
    if isinstance(a, dict):
        return "definitely wrong"
    if isinstance(a, list):
        return [i for i in range(len(q["choices"])) if i not in a][:1] or [0]
    return (a + 1) % len(q["choices"])


def run(client, t, strategy, **start):
    view = client.post(f"/api/v1/transitions/{t['id']}/assessments", json=start).json()
    served = []
    while view["status"] == "in_progress":
        q = view["question"]
        served.append(q)
        r = client.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": strategy(q)})
        assert r.status_code == 200, r.text
        view = r.json()
    return view, served


def test_blueprint_targets_job_requirements(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    items = {i["skill_id"]: i for i in view["blueprint"]["items"]}
    assert items["sql"]["importance"] == "mandatory" and items["sql"]["min_questions"] == 2
    assert items["excel"]["importance"] == "mandatory" and items["statistics"]["importance"] == "mandatory"
    assert items["pandas"]["importance"] == "preferred" and items["pandas"]["min_questions"] == 1
    assert "communication" in {u["skill_id"] for u in view["blueprint"]["uncovered"]}
    assert view["question"]["skill_id"] in items


def test_answer_key_never_leaves_server_mid_attempt(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    for _ in range(4):
        q = view["question"]
        dumped = json.dumps(view)
        assert "correct_answer" not in dumped and "explanation" not in dumped
        assert KEY[q["id"]]["explanation"] not in dumped
        view = guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": right(q)}).json()
        assert "is_correct" not in json.dumps(view)
    assert guest.get(f"/api/v1/assessments/{view['id']}/review").status_code == 409


def test_only_current_question_answerable_once(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    q = view["question"]
    other = next(qid for qid in KEY if qid != q["id"])
    assert guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": other, "response": 0}).status_code == 409
    assert guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": right(q)}).status_code == 200
    r = guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": right(q)})
    assert r.status_code == 409


def test_invalid_answer_format(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    q = view["question"]
    bad = "text" if q["choices"] else 12345
    r = guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": bad})
    assert r.status_code == 422


def test_full_correct_run_covers_mandatory_and_scores_high(guest):
    t = full_intake(guest)
    view, served = run(guest, t, right)
    res = view["results"]
    assert view["status"] == "completed" and res["coverage"]["mandatory_complete"]
    for sid in ("sql", "excel", "statistics"):
        s = res["skills"][sid]
        assert s["answered"] >= 2 and s["confidence"] != "insufficient" and s["score"] >= 50
    assert len(served) <= view["blueprint"]["budget"]
    assert "not a validated measure" in res["disclaimer"]
    review = guest.get(f"/api/v1/assessments/{view['id']}/review").json()
    assert all("correct_answer" in r and r["explanation"] for r in review)


def test_insufficient_evidence_has_no_numeric_score(guest):
    t = full_intake(guest)
    view, _ = run(guest, t, right)
    for s in view["results"]["skills"].values():
        if s["answered"] < 2:
            assert s["score"] is None and s["confidence"] == "insufficient"


def test_difficulty_adapts(guest):
    t = full_intake(guest)
    _, up = run(guest, t, right)
    t2 = full_intake(guest, role="Data Analyst")
    _, down = run(guest, t2, wrong)
    sql_up = [q["difficulty"] for q in up if q["skill_id"] == "sql"]
    sql_down = [q["difficulty"] for q in down if q["skill_id"] == "sql"]
    assert sql_up == sorted(sql_up) and sql_up[-1] > sql_up[0]
    assert sql_down[-1] <= sql_down[0]


def test_wrong_answers_give_low_proficiency_and_bigger_gaps(guest):
    t = full_intake(guest)
    before = {i["skill_id"]: i for i in guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()["items"]}
    view, _ = run(guest, t, wrong)
    assert view["results"]["skills"]["excel"]["score"] < 30
    after = guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()
    items = {i["skill_id"]: i for i in after["items"]}
    assert items["excel"]["basis"] == "assessed"
    assert items["excel"]["gap"] > before["excel"]["gap"]  # the quiz overrides the resume claim


def test_finish_blocked_until_mandatory_covered(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    r = guest.post(f"/api/v1/assessments/{view['id']}/finish")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "COVERAGE_INCOMPLETE"


def test_restart_resumes_in_progress_attempt(guest):
    t = full_intake(guest)
    a = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    b = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    assert a["id"] == b["id"] and a["question"]["id"] == b["question"]["id"]


def test_rotation_prefers_unseen_questions(guest):
    t = full_intake(guest)
    _, first = run(guest, t, right)
    _, second = run(guest, t, right)
    first_ids = {q["id"] for q in first}
    new = [q for q in second if q["id"] not in first_ids]
    assert len(new) >= len(second) // 2


def test_timed_question_late_answer_scores_zero(guest):
    t = full_intake(guest)
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={"timed": True, "seconds_per_question": 30}).json()
    assert view["time_left"] is not None and view["time_left"] <= 30
    with SessionLocal() as db:
        a = db.get(AssessmentAttempt, view["id"])
        a.current_served_at = utcnow() - timedelta(seconds=120)
        db.commit()
    q = view["question"]
    guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q["id"], "response": right(q)})
    # finish the rest correctly, then check the late one was marked wrong
    view = guest.get(f"/api/v1/assessments/{view['id']}").json()
    while view["status"] == "in_progress":
        q2 = view["question"]
        view = guest.post(f"/api/v1/assessments/{view['id']}/answer", json={"question_id": q2["id"], "response": right(q2)}).json()
    late = next(r for r in guest.get(f"/api/v1/assessments/{view['id']}/review").json() if r["id"] == q["id"])
    assert late["timed_out"] and late["score"] == 0


def test_topic_check_single_skill(guest):
    t = full_intake(guest)
    view, served = run(guest, t, right, kind="topic_check", skill_id="sql")
    assert {q["skill_id"] for q in served} == {"sql"} and len(served) >= 3
    assert list(view["results"]["skills"]) == ["sql"]


def test_practical_questions_skipped_without_ai_evaluator(guest):
    t = full_intake(guest)
    _, served = run(guest, t, right)
    assert all(q["type"] != "practical" for q in served)


def test_skills_without_questions_listed_as_uncovered(guest):
    t = full_intake(guest, role="UX Designer")
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "role"})
    view = guest.post(f"/api/v1/transitions/{t['id']}/assessments", json={}).json()
    uncovered = {u["skill_id"]: u["reason"] for u in view["blueprint"]["uncovered"]}
    assert r.json()["status"] == "ok"
    assert "figma" in uncovered and "ux-design" in uncovered
