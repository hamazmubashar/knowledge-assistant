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
    stuck_timeout_minutes: int = 30
    ocr_provider: str = "tesseract"
    ocr_min_chars: int = 10
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str = "/models"
    generation_provider: str = "ollama"
    generation_model: str = "qwen2.5:3b"
    ollama_base_url: str = "http://host.docker.internal:11434"
    generation_timeout_seconds: int = 180
    answer_max_distance: float = 0.30


settings = Settings()