import io


def make_pdf(lines: list[str]) -> bytes:
    """A minimal valid single-page PDF with extractable text (no external libraries)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = "BT /F1 10 Tf 40 800 Td 12 TL " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_docx(lines: list[str]) -> bytes:
    import docx

    d = docx.Document()
    for line in lines:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def setup_transition(client, role="Junior Data Analyst", weekly_hours=6, **extra):
    body = {"title": "Into data", "target_role": role, "weekly_hours": weekly_hours, "current_role": "Teacher", **extra}
    r = client.post("/api/v1/transitions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def full_intake(client, **extra):
    from app.seed.demo_content import DEMO_JOB, DEMO_RESUME

    t = setup_transition(client, **extra)
    assert client.post("/api/v1/resumes/text", json={"text": DEMO_RESUME}).status_code == 201
    r = client.post(f"/api/v1/transitions/{t['id']}/job", json={"mode": "paste", "text": DEMO_JOB, "title": "Junior Data Analyst"})
    assert r.json()["status"] == "ok", r.text
    r = client.post(f"/api/v1/transitions/{t['id']}/analysis", json={})
    assert r.status_code == 201, r.text
    return t
