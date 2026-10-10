from contextlib import asynccontextmanager
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import boto3
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.api import answer, auth, documents, me, search
from app.db.session import SessionLocal
from app.services.embeddings import ensure_active_index, get_embedder
from app.core.config import settings
from app.services import storage
from app.services.generation import get_generator


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure_bucket()
    app.state.embedder = get_embedder()
    with SessionLocal() as db:
        app.state.index_id = ensure_active_index(db, app.state.embedder)
    app.state.generator = get_generator()
    app.state.judge = get_generator(settings.judge_model) if settings.judge_model else None
    yield


app = FastAPI(title="Knowledge Assistant", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(auth.router)
app.include_router(search.router)
app.include_router(answer.router)
app.include_router(me.router)

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

UI_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
          "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")


@app.middleware("http")
async def ui_security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Content-Security-Policy"] = UI_CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(STATIC / "index.html")

@app.get("/health/live")
def live():
    return {"status": "alive"}

@app.get("/health/ready")
def health():
    checks = {}
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name="us-east-1",
        )
        s3.list_buckets()
        checks["storage"] = "ok"
    except Exception:
        checks["storage"] = "error"
    status = 200 if all(v == "ok" for v in checks.values()) else 503
    return JSONResponse(status_code=status, content=checks)