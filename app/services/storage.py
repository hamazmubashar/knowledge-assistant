import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        region_name="us-east-1",
    )


def ensure_bucket():
    c = _client()
    try:
        c.head_bucket(Bucket=settings.storage_bucket)
    except ClientError:
        c.create_bucket(Bucket=settings.storage_bucket)


def put_pdf(key: str, data: bytes):
    _client().put_object(Bucket=settings.storage_bucket, Key=key, Body=data,
                         ContentType="application/pdf")


def download_to(key: str, path: str):
    _client().download_file(settings.storage_bucket, key, path)