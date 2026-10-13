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
    database_url: str = Field(default="sqlite:///./student.db", min_length=1)
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)
    openai_timeout_seconds: float = Field(default=30, gt=0, le=120)
    guidance_max_output_tokens: int = Field(default=1200, ge=100, le=4000)
    guidance_history_turns: int = Field(default=10, ge=0, le=50)
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
