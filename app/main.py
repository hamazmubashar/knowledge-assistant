import boto3
import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import settings

app = FastAPI(title="Knowledge Assistant")

@app.get("/health")
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