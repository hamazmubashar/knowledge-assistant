import time
import uuid
from sqlalchemy import delete
from app.db.models import Document

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.models import AccessGroup, AdminScope, Role, User
from app.db.session import SessionLocal
from app.main import app

PASSWORD = "Test-Password-123"
TAG = uuid.uuid4().hex[:6]

DOCS = {
    "hr": ("Compensation and discipline", [
        "SALARY BANDS",
        "Salary bands are reviewed every April. Band C ranges from 4,000 to 5,500 per month.",
        "DISCIPLINARY PROCEDURE",
        "Serious misconduct leads to a written warning and may freeze the next pay increase."]),
    "support": ("Customer refunds", [
        "REFUND PROCEDURE",
        "Customers may request a full refund within 30 days of purchase.",
        "Refunds are issued to the original payment method within 5 working days."]),
    "operations": ("Warehouse handover", [
        "SHIFT HANDOVER",
        "The outgoing supervisor completes the handover checklist before 18:00.",
        "Damaged stock is logged in the inventory system before the shift ends."]),
    "general": ("Office information", [
        "OPENING HOURS",
        "The office is open from 09:00 to 17:00, Monday to Friday."]),
}


def make_user(role, groups=()):
    email = f"rt-{role.value}-{uuid.uuid4().hex[:8]}@local.test"
    with SessionLocal() as db:
        u = User(email=email, password_hash=hash_password(PASSWORD), role=role)
        db.add(u)
        db.flush()
        for g in groups:
            db.add(AdminScope(user_id=u.id, access_group=g))
        db.commit()
    return email


def auth(c, email):
    r = c.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def pdf(lines):
    d = pymupdf.open()
    page = d.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + i * 18), line, fontsize=11)
    data = d.tobytes()
    d.close()
    return data


@pytest.fixture(scope="module")
def env():
    with TestClient(app) as c:
        admin = auth(c, make_user(Role.hr, list(AccessGroup)))
        users = {r: auth(c, make_user(r))
                 for r in (Role.support, Role.operations, Role.hr, Role.system_admin)}
        doc_ids, version_ids = {}, []
        for group, (title, lines) in DOCS.items():
            r = c.post("/documents", headers=admin,
                       data={"title": f"{title} {TAG}", "access_group": group},
                       files={"file": (f"{group}.pdf", pdf(lines), "application/pdf")})
            assert r.status_code == 201
            doc_ids[group] = r.json()["document_id"]
            version_ids.append(r.json()["version_id"])
        deadline = time.time() + 90
        for vid in version_ids:
            while c.get(f"/versions/{vid}", headers=admin).json()["status"] != "published":
                assert time.time() < deadline, "worker did not publish test documents in time"
                time.sleep(1)
        yield c, users, doc_ids
        with SessionLocal() as db:
            db.execute(delete(Document).where(
                Document.id.in_([uuid.UUID(x) for x in doc_ids.values()])))
            db.commit()


def search(c, headers, q):
    r = c.post("/search", headers=headers, json={"query": q, "k": 5})
    assert r.status_code == 200
    return r.json()["results"]


def test_no_token_is_rejected(env):
    c, _, _ = env
    assert c.post("/search", json={"query": "refund"}).status_code == 401


def test_support_never_sees_hr_even_with_indirect_wording(env):
    c, u, _ = env
    for q in ["salary bands", "What is the pay range for band C?",
              "will a warning affect my next raise", "disciplinary procedure"]:
        assert all(r["access_group"] != "hr" for r in search(c, u[Role.support], q)), q


def test_operations_sees_support_but_not_hr(env):
    c, u, d = env
    res = search(c, u[Role.operations], "How long do customers have to ask for a refund?")
    assert d["support"] in [r["document_id"] for r in res]
    for q in ["salary bands", "what happens to my pay after misconduct"]:
        assert all(r["access_group"] != "hr" for r in search(c, u[Role.operations], q)), q


def test_hr_finds_hr_content(env):
    c, u, d = env
    res = search(c, u[Role.hr], "What is the salary range for band C?")
    assert d["hr"] in [r["document_id"] for r in res[:3]]


def test_hr_cannot_see_support_content(env):
    c, u, _ = env
    res = search(c, u[Role.hr], "refund within 30 days")
    assert all(r["access_group"] in ("hr", "general") for r in res)


def test_everyone_sees_general(env):
    c, u, d = env
    res = search(c, u[Role.support], "office opening hours")
    assert d["general"] in [r["document_id"] for r in res]


def test_system_admin_sees_no_documents(env):
    c, u, _ = env
    assert search(c, u[Role.system_admin], "refund") == []


def test_results_carry_full_citation_chain(env):
    c, u, _ = env
    r = search(c, u[Role.hr], "salary bands")[0]
    for key in ("chunk_id", "document_id", "version_id", "version_number",
                "page_number", "chunk_index"):
        assert r[key] is not None, key