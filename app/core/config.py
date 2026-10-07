from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)
    database_url: str
    storage_endpoint: str | None = None
    storage_access_key: str
    storage_secret_key: str
    storage_bucket: str = "documents"
    max_upload_mb: int = 50
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = 60


settings = Settings()