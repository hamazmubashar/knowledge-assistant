import time
import uuid

import httpx
import pymupdf
from sqlalchemy import text

from app.core.security import hash_password
from app.db.models import AccessGroup, AdminScope, Role, User
from app.db.session import SessionLocal

BASE = "http://localhost:8000"
PW = "Demo-Password-123!"
results = []


def record(n, name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {n}. {name}  {detail}")


def sql(query, **params):
    with SessionLocal() as db:
        r = db.execute(text(query), params)
        db.commit()
        return r


def make_user(role, groups=()):
    email = f"demo-{role.value}-{uuid.uuid4().hex[:6]}@local.test"
    with SessionLocal() as db:
        u = User(email=email, password_hash=hash_password(PW), role=role)
        db.add(u)
        db.flush()
        for g in groups:
            db.add(AdminScope(user_id=u.id, access_group=g))
        db.commit()
    return email


def login(c, email):
    r = c.post("/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def pdf_bytes(label, pages):
    d = pymupdf.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"{label} page {i + 1}")
    data = d.tobytes()
    d.close()
    return data


def wait_status(c, h, vid, targets, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        s = c.get(f"/versions/{vid}", headers=h).json()
        if s["status"] in targets:
            return s
        time.sleep(1)
    return c.get(f"/versions/{vid}", headers=h).json()


def main():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        hr_admin = login(c, make_user(Role.hr, [AccessGroup.hr, AccessGroup.general]))
        hr_user = login(c, make_user(Role.hr))
        support = login(c, make_user(Role.support))

        r = c.post("/documents", headers=hr_admin,
                   data={"title": "Demo HR policy", "access_group": "hr"},
                   files={"file": ("hr.pdf", pdf_bytes("Synthetic HR policy", 3), "application/pdf")})
        vid, doc_id = r.json()["version_id"], r.json()["document_id"]
        s = wait_status(c, hr_admin, vid, {"ready", "failed"})
        record(1, "Valid PDF -> ingested", s["status"] == "ready" and s["page_count"] == 3,
               f"status={s['status']} pages={s['page_count']}")

        r = c.post("/documents", headers=hr_admin,
                   data={"title": "Fake", "access_group": "general"},
                   files={"file": ("evil.pdf", b"MZ fake executable", "application/pdf")})
        record(2, "Invalid/malicious file -> rejected", r.status_code == 400,
               f"http={r.status_code} detail={r.json().get('detail')}")

        key = sql("SELECT storage_key FROM document_versions WHERE id=:v", v=vid).scalar()
        sql("UPDATE document_versions SET status='failed', storage_key='missing/x.pdf' WHERE id=:v", v=vid)
        c.post(f"/versions/{vid}/retry", headers=hr_admin)
        s = wait_status(c, hr_admin, vid, {"failed"})
        record(3, "Worker failure -> Failed", s["status"] == "failed" and s["error_step"] == "download",
               f"step={s['error_step']} error={s['error_message']}")

        sql("UPDATE document_versions SET storage_key=:k WHERE id=:v", k=key, v=vid)
        c.post(f"/versions/{vid}/retry", headers=hr_admin)
        s = wait_status(c, hr_admin, vid, {"ready"})
        pages = sql("SELECT count(*) FROM pages WHERE version_id=:v", v=vid).scalar()
        record(4, "Retry -> completes, no duplicates", s["status"] == "ready" and pages == 3,
               f"status={s['status']} pages={pages} attempts={s['attempts']}")

        sql("UPDATE document_versions SET status='processing', "
            "processing_started_at = now() - interval '31 minutes' WHERE id=:v", v=vid)
        s = wait_status(c, hr_admin, vid, {"failed"}, timeout=20)
        record(5, "Stuck 31 min -> Failed by 30-min timeout",
               s["status"] == "failed" and s["error_step"] == "timeout", f"step={s['error_step']}")
        c.post(f"/versions/{vid}/retry", headers=hr_admin)
        wait_status(c, hr_admin, vid, {"ready"})

        a = c.get(f"/versions/{vid}", headers=support).status_code
        b = c.get(f"/versions/{vid}/file", headers=support).status_code
        record(6, "Support -> HR document denied", a == 404 and b == 404, f"view={a} file={b}")

        r = c.get(f"/versions/{vid}/file", headers=hr_user)
        record(7, "HR user -> HR document allowed",
               r.status_code == 200 and r.content.startswith(b"%PDF-"), f"http={r.status_code}")

        a = c.get(f"/versions/{vid}/file").status_code
        b = c.get(f"/versions/{vid}/file", headers={"Authorization": "Bearer forged.token.x"}).status_code
        record(8, "No file access without valid login", a == 401 and b == 401,
               f"no_token={a} forged={b}")

        print("[INFO] 9. Logs: run the separate log-audit command")

        row = sql(
            "SELECT d.access_group, v.document_id, v.page_count, count(p.id) AS pages "
            "FROM documents d JOIN document_versions v ON v.document_id = d.id "
            "LEFT JOIN pages p ON p.version_id = v.id WHERE d.id = :d "
            "GROUP BY d.access_group, v.document_id, v.page_count", d=doc_id).one()
        ok = row.access_group == "hr" and str(row.document_id) == doc_id and row.page_count == row.pages == 3
        record(10, "DB document/version/page/group links", ok,
               f"group={row.access_group} page_count={row.page_count} pages={row.pages}")

    print(f"\n{sum(results)}/{len(results)} automated scenarios passed")


if __name__ == "__main__":
    main()