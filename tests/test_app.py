import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.pop("OPENAI_API_KEY", None)

from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    return create_app({"DATABASE": str(tmp_path / "t.db"), "SEED_DEMO": True, "TESTING": True})


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
