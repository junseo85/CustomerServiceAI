import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.pop("OPENAI_API_KEY", None)

from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"DATABASE": str(tmp_path / "t.db"), "SEED_DEMO": True, "TESTING": True,
                       "UPLOAD_DIR": str(tmp_path / "up")})


def login(client, user):
    client.get("/login")
    with client.session_transaction() as s:
        s["csrf"] = "tok"
    client.post("/login", data={"username": user, "password": "password", "csrf_token": "tok"})
    with client.session_transaction() as s:
        s["csrf"] = "tok"
    return {"X-CSRF-Token": "tok"}


def report(client, h):
    msgs = [{"role": "user", "content": "Printer down in QA lab"}]
    r = client.post("/api/chat", json={"messages": msgs, "language": "ko"}, headers=h)
    assert r.json["ready"] is False
    msgs += [{"role": "assistant", "content": r.json["reply"]}, {"role": "user", "content": "Urgent, building 2"}]
    r = client.post("/api/chat", json={"messages": msgs, "language": "ko"}, headers=h)
    assert r.json["ready"] is True
    return r.json["issue_id"]


def test_requires_login(app):
    assert app.test_client().get("/issues").status_code == 302


def test_csrf_enforced(app):
    c = app.test_client()
    login(c, "employee")
    assert c.post("/api/chat", json={}).status_code == 400


def test_chat_creates_issue_visible_to_staff_only_to_own_employee(app):
    emp, it = app.test_client(), app.test_client()
    h = login(emp, "employee")
    iid = report(emp, h)
    login(it, "it")
    assert b"Printer down" in it.get("/issues").data
    assert it.get(f"/issues/{iid}").status_code == 200
    login(c := app.test_client(), "employee")
    assert c.get(f"/issues/{iid}").status_code == 200


def test_employee_cannot_change_status(app):
    c = app.test_client()
    h = login(c, "employee")
    iid = report(c, h)
    assert c.post(f"/issues/{iid}/status", data={"status": "closed"}, headers=h).status_code == 403


def test_staff_status_and_translate(app):
    emp, qa = app.test_client(), app.test_client()
    iid = report(emp, login(emp, "employee"))
    h = login(qa, "qa")
    assert qa.post(f"/issues/{iid}/status", data={"status": "resolved"}, headers=h).status_code == 302
    r = qa.post("/api/translate", json={"text": "hello", "language": "es"}, headers=h)
    assert r.json["text"].startswith("[es]")
    assert qa.post("/api/translate", json={"text": "x", "language": "zz"}, headers=h).status_code == 400


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def upload(c, h, name="shot.png", data=PNG):
    import io
    return c.post("/api/attachments", data={"file": (io.BytesIO(data), name)}, headers=h,
                  content_type="multipart/form-data")


def test_attachment_flow_linked_to_ticket_and_access_controlled(app):
    emp, other, it = app.test_client(), app.test_client(), app.test_client()
    h = login(emp, "employee")
    r = upload(emp, h)
    assert r.status_code == 201
    att = r.json
    assert emp.get(att["url"]).status_code == 200
    ho = login(other, "qa")
    assert other.get(att["url"]).status_code == 404  # pending upload is private
    msgs = [{"role": "user", "content": "Printer down"}]
    r1 = emp.post("/api/chat", json={"messages": msgs, "language": "en", "attachment_ids": [att["id"]],
                                    "new_attachment_ids": [att["id"]]}, headers=h)
    msgs += [{"role": "assistant", "content": r1.json["reply"]}, {"role": "user", "content": "urgent"}]
    r2 = emp.post("/api/chat", json={"messages": msgs, "language": "en", "attachment_ids": [att["id"]]}, headers=h)
    iid = r2.json["issue_id"]
    assert b"shot.png" in emp.get(f"/issues/{iid}").data
    assert other.get(att["url"]).status_code == 200  # staff can view
    login(it, "it")
    assert it.get(att["url"]).headers["X-Content-Type-Options"] == "nosniff"


def test_upload_validation(app):
    c = app.test_client()
    h = login(c, "employee")
    assert upload(c, h, "evil.exe", b"MZ").status_code == 400
    assert upload(c, h, "fake.png", b"<html>").status_code == 400
    assert upload(c, h, "big.png", PNG + b"0" * (11 * 1024 * 1024)).status_code == 413
    assert app.test_client().post("/api/attachments").status_code in (400, 401)
