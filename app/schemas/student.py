from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    assessment_answers: dict[str, JsonValue] = Field(default_factory=dict)


class StudentRead(StudentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_as_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
