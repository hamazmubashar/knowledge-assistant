import uuid

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.models import AccessGroup, AdminScope, Role, User
from app.db.session import SessionLocal
from app.main import app

PASSWORD = "Test-Password-123"


def make_user(role, admin_groups=()):
    email = f"test-{role.value}-{uuid.uuid4().hex[:8]}@local.test"
    with SessionLocal() as db:
        u = User(email=email, password_hash=hash_password(PASSWORD), role=role)
        db.add(u)
        db.flush()
        for g in admin_groups:
            db.add(AdminScope(user_id=u.id, access_group=g))
        db.commit()
    return email


def auth(client, email):
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def synthetic_pdf() -> bytes:
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "Synthetic HR policy for testing")
    data = d.tobytes()
    d.close()
    return data


@pytest.fixture(scope="module")
def env():
    with TestClient(app) as client:
        hr_admin = make_user(Role.hr, [AccessGroup.hr])
        hr_user = make_user(Role.hr)
        support_user = make_user(Role.support)
        r = client.post("/documents", headers=auth(client, hr_admin),
                        data={"title": "HR policy (synthetic)", "access_group": "hr"},
                        files={"file": ("hr.pdf", synthetic_pdf(), "application/pdf")})
        assert r.status_code == 201
        yield client, r.json()["version_id"], hr_user, support_user


def test_no_token_is_rejected(env):
    client, vid, _, _ = env
    assert client.get(f"/versions/{vid}").status_code == 401


def test_forged_token_is_rejected(env):
    client, vid, _, _ = env
    r = client.get(f"/versions/{vid}", headers={"Authorization": "Bearer not.a.real.token"})
    assert r.status_code == 401


def test_support_cannot_see_hr_version(env):
    client, vid, _, support = env
    assert client.get(f"/versions/{vid}", headers=auth(client, support)).status_code == 404


def test_support_cannot_download_hr_file(env):
    client, vid, _, support = env
    assert client.get(f"/versions/{vid}/file", headers=auth(client, support)).status_code == 404


def test_hr_user_can_see_hr_version(env):
    client, vid, hr, _ = env
    assert client.get(f"/versions/{vid}", headers=auth(client, hr)).status_code == 200


def test_hr_user_can_download_hr_file(env):
    client, vid, hr, _ = env
    r = client.get(f"/versions/{vid}/file", headers=auth(client, hr))
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_support_cannot_upload_hr_document(env):
    client, _, _, support = env
    r = client.post("/documents", headers=auth(client, support),
                    data={"title": "x", "access_group": "hr"},
                    files={"file": ("x.pdf", synthetic_pdf(), "application/pdf")})
    assert r.status_code == 403


def test_guessed_version_id_returns_404(env):
    client, _, hr, _ = env
    r = client.get(f"/versions/{uuid.uuid4()}", headers=auth(client, hr))
    assert r.status_code == 404