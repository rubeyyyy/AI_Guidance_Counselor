from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_name: str = Field(default="AI Guidance Counselor - Student API", min_length=1)
    database_url: str = Field(default="sqlite:///./student.db", min_length=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
