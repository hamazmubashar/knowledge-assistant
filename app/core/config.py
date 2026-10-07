from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    storage_endpoint: str | None = None
    storage_access_key: str
    storage_secret_key: str
    storage_bucket: str = "documents"
    max_upload_mb: int = 50

settings = Settings()