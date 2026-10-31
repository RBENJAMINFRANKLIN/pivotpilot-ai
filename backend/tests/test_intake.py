import io
import zipfile

import pytest

from app.security.netfetch import FetchBlocked, FetchResult, safe_get
from app.seed.demo_content import DEMO_JOB, DEMO_RESUME
from tests.helpers import full_intake, make_docx, make_pdf, setup_transition

RESUME_LINES = DEMO_RESUME.splitlines()


def upload(client, name, data, ctype="application/octet-stream"):
    return client.post("/api/v1/resumes/upload", files={"file": (name, data, ctype)})


def test_pdf_upload_extracts_sections_and_skills(guest):
    r = upload(guest, "cv.pdf", make_pdf(RESUME_LINES), "application/pdf")
    assert r.status_code == 201, r.text
    body = r.json()
    ex = body["extracted"]
    assert body["source"] == "pdf" and body["version_number"] == 1
    assert {"experience", "education", "skills", "summary"} <= set(ex["sections"])
    skills = {s["skill_id"] for s in ex["skills"]}
    assert {"excel", "statistics", "communication"} <= skills
    assert "sql" not in skills  # never invented
    assert ex["total_years_experience"] and ex["total_years_experience"] > 8
    for s in ex["skills"]:  # every skill is backed by text that is really in the resume
        for e in s["evidence"]:
            assert e["excerpt"].lower()[:30] in body["text_content"].lower()


def test_docx_upload(guest):
    r = upload(guest, "cv.docx", make_docx(RESUME_LINES))
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "docx"


@pytest.mark.parametrize("name,data,code", [
    ("cv.pdf", b"", "EMPTY_FILE"),
    ("cv.exe", b"MZ\x90\x00 not a resume", "UNSUPPORTED_TYPE"),
    ("cv.docx", make_pdf(["hello"]), "EXTENSION_MISMATCH"),
    ("cv.pdf", b"PK\x03\x04garbage", "UNSUPPORTED_TYPE"),
    ("cv.pdf", b"%PDF-1.4 this is not really a pdf", "MALFORMED_FILE"),
    ("cv.docx", b"PK\x03\x04 broken zip", "MALFORMED_FILE"),
    ("cv.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", "UNSUPPORTED_TYPE"),
])
def test_invalid_files_rejected_safely(guest, name, data, code):
    r = upload(guest, name, data)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == code
    assert guest.get("/api/v1/resumes").json() == []


def test_oversized_file_rejected(guest):
    r = upload(guest, "cv.pdf", b"%PDF-" + b"0" * (6 * 1024 * 1024))
    assert r.status_code in (400, 413)


def test_macro_docx_rejected(guest):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/vbaProject.bin", "macro")
    r = upload(guest, "cv.docx", buf.getvalue())
    assert r.json()["detail"]["code"] == "MACROS_NOT_ALLOWED"


def test_scanned_pdf_without_text_rejected(guest):
    r = upload(guest, "cv.pdf", make_pdf([""]))
    assert r.json()["detail"]["code"] == "NO_TEXT"


def test_upload_rate_limited(guest):
    for _ in range(6):
        guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME})
    assert guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).status_code in (403, 429)


def test_resume_versions_and_edit_history(guest):
    v1 = guest.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).json()
    edit = {"experiences": v1["extracted"]["experiences"], "education": v1["extracted"]["education"],
            "skills": [{"skill_id": s["skill_id"]} for s in v1["extracted"]["skills"]] + [{"skill_id": "sql", "excerpt": "Wrote SQL at a volunteer project"}],
            "total_years_experience": 9}
    r = guest.put(f"/api/v1/resumes/{v1['id']}/extracted", json=edit)
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["version_number"] == 2 and v2["parent_version_id"] == v1["id"] and v2["is_user_edited"]
    assert "sql" in {s["skill_id"] for s in v2["extracted"]["skills"]}
    assert [v["version_number"] for v in guest.get("/api/v1/resumes").json()] == [2, 1]
    r = guest.put(f"/api/v1/resumes/{v1['id']}/extracted", json={**edit, "skills": [{"skill_id": "not-a-skill"}]})
    assert r.status_code == 422


def test_job_url_falls_back_to_paste_when_blocked(guest):
    t = setup_transition(guest)
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "url", "url": "https://www.linkedin.com/jobs/view/123"})
    assert r.json()["status"] == "needs_paste" and "paste" in r.json()["message"].lower()
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "url", "url": "http://127.0.0.1:8000/admin"})
    assert r.json()["status"] == "needs_paste"
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "paste", "text": DEMO_JOB})
    assert r.json()["status"] == "ok"


def test_job_url_expired_and_ok(guest, monkeypatch):
    import app.services.jobs as jobs

    t = setup_transition(guest)
    monkeypatch.setattr(jobs, "safe_get", lambda url, **k: FetchResult(url, 404, "text/html", "<h1>Gone</h1>"))
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "url", "url": "https://jobs.example.com/1"})
    assert r.json()["status"] == "needs_paste" and "removed" in r.json()["message"]
    html = "<html><body><h1>Data Analyst</h1><main>" + DEMO_JOB.replace("\n", "<br>\n") + "</main></body></html>"
    monkeypatch.setattr(jobs, "safe_get", lambda url, **k: FetchResult(url, 200, "text/html", html))
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "url", "url": "https://jobs.example.com/2"})
    body = r.json()
    assert body["status"] == "ok"
    assert all(req["source_url"] == "https://jobs.example.com/2" for req in body["job"]["requirements"])


def test_ssrf_protection():
    for url in ("http://127.0.0.1/", "http://localhost/x", "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data",
                "file:///etc/passwd", "http://user:pw@example.com/", "http://example.com:8080/"):
        with pytest.raises(FetchBlocked):
            safe_get(url)


def test_competency_map_has_evidence_and_importance(guest):
    t = setup_transition(guest)
    job = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "paste", "text": DEMO_JOB}).json()["job"]
    reqs = {r["skill_id"]: r for r in job["requirements"] if r["skill_id"]}
    assert reqs["sql"]["importance"] == "mandatory" and "SQL" in reqs["sql"]["source_excerpt"]
    assert reqs["excel"]["importance"] == "mandatory"
    assert reqs["pandas"]["importance"] == "preferred"
    assert reqs["tableau"]["importance"] in ("mandatory", "preferred")
    for r in job["requirements"]:
        assert r["source_excerpt"] and r["source_excerpt"].lower()[:25] in DEMO_JOB.lower()
    cats = {r["category"] for r in job["requirements"]}
    assert {"experience", "education", "responsibility", "skill", "tool", "professional"} <= cats
    assert reqs["pandas"]["prerequisite_skill_ids"] == ["python"]


def test_role_only_template_is_labelled(guest):
    t = setup_transition(guest, role="Data Analyst")
    r = guest.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "role"}).json()
    assert r["status"] == "ok" and "template" in r["message"].lower()
    assert all(req["source_excerpt"] is None for req in r["job"]["requirements"])
    t2 = setup_transition(guest, role="Astronaut")
    assert guest.post(f"/api/v1/transitions/{t2['id']}/job", json={"mode": "role"}).json()["status"] == "needs_paste"


def test_evidence_linked_fit_analysis(guest):
    t = full_intake(guest)
    a = guest.get(f"/api/v1/transitions/{t['id']}/analysis").json()
    ev = {e["skill_id"]: e for e in a["requirement_evidence"] if e["skill_id"]}
    assert ev["excel"]["status"] == "demonstrated" and "pivot tables" in ev["excel"]["resume_excerpts"][0]
    assert ev["sql"]["status"] in ("missing", "transferable")
    assert ev["statistics"]["status"] in ("demonstrated", "listed")
    assert 0 < a["fit_score"] < 100
    assert 0 < a["quality_score"] <= 100
    assert sum(c["max"] for c in a["quality_breakdown"]["components"]) == 100
    assert "not a hiring probability" in a["fit_breakdown"]["caveat"]
    assert a["experience_alignment"]["status"] == "met"
    assert any("SQL" in s["text"] for s in a["suggestions"])
    # Resume quality is independent of the job; fit depends on it.
    assert a["quality_score"] != a["fit_score"]


def test_gaps_are_provisional_before_assessment(guest):
    t = full_intake(guest)
    gaps = guest.get(f"/api/v1/transitions/{t['id']}/gaps").json()
    assert gaps["status"] == "provisional"
    sql = next(i for i in gaps["items"] if i["skill_id"] == "sql")
    assert sql["basis"] == "provisional" and sql["gap"] > 50
    r = guest.get(f"/api/v1/transitions/{t['id']}/readiness").json()
    assert r["provisional"] is True and "assessed_proficiency" in r["missing_components"]
