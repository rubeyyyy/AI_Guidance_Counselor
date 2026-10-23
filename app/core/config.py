from functools import lru_cache
from pathlib import Path

from typing import Literal
from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "production"] = "development"
    auth_dev_commands: bool = False
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_hours: int = Field(default=8, ge=1, le=24)
    auth_rate_limit: int = Field(default=10, ge=1, le=100)
    auth_ip_rate_limit: int = Field(default=300, ge=1, le=10000)

    auth_code_secret: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "tls"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: EmailStr | None = None
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=30)

    @field_validator("smtp_from", mode="before")
    @classmethod
    def blank_sender(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_security(self):
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("Production requires COOKIE_SECURE=true")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")
        if not self.cors_origins or any("*" in origin or origin.endswith("/") for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain explicit origins without trailing slashes")
        if self.environment == "production" and any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("Production trusted origins must use HTTPS")
        if self.smtp_host and (not self.smtp_from or len(self.auth_code_secret.get_secret_value()) < 32):
            raise ValueError("Email delivery requires SMTP_FROM and an AUTH_CODE_SECRET of at least 32 characters")
        if bool(self.smtp_username) != bool(self.smtp_password.get_secret_value()):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        return self

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
    guidance_questionnaire_id: str = "initial-v2"
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
        "short_term_timeline", "long_term_timeline", "confidence", "primary_motivator", "other_motivator",
        "knows_tutoring_resources", "knows_how_to_find_internship", "knows_job_training_resources",
        "has_talked_to_career_adult", "knows_required_education", "clubs_competitions_projects",
        "related_experiences", "certifications", "career_interest_reason",
    ])


@lru_cache
def get_settings() -> Settings:
    return Settings()
