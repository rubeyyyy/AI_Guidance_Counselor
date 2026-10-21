from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_name: str = Field(default="AI Guidance Counselor - Student API", min_length=1)
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173",
    ])
    database_url: str = Field(default="sqlite:///./student.db", min_length=1)
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    guidance_max_output_tokens: int = Field(default=1200, ge=100, le=4000)
    guidance_history_turns: int = Field(default=10, ge=0, le=50)
    openai_embedding_model: str = Field(default="text-embedding-3-small", min_length=1)
    chroma_persist_directory: Path = PROJECT_ROOT / "chroma_data"
    rag_enabled: bool = False
    rag_top_k: int = Field(default=4, ge=1, le=20)
    rag_chunk_size: int = Field(default=1000, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=150, ge=0, lt=200)
    rag_score_threshold: float = Field(default=0.35, ge=0, le=1)
    # Explicitly reviewed keys only. Add exact keys when the real form is ready.
    guidance_profile_keys: list[str] = Field(default_factory=lambda: [
        "sample_text", "sample_number", "sample_choice", "sample_choices",
        "interests", "academic_background", "grade", "current_program", "gpa",
        "career_aspirations", "short_term_goal", "long_term_aspirations",
        "skills", "soft_skills", "technical_skills", "learning_preferences",
        "resources", "constraints", "has_personal_laptop", "has_reliable_internet",
        "weekly_learning_hours", "biggest_obstacle", "accessibility_needs",
        "socioeconomic_factors", "other_obstacle", "technical_skills_raw",
        "related_experiences", "certifications", "career_interest_reason",
    ])


@lru_cache
def get_settings() -> Settings:
    return Settings()
