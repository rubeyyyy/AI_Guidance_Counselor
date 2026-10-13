from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.student import StudentRead


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = Field(default=None, gt=0, strict=True)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "completed", "failed"]
    reply_to_message_id: int | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_as_utc(cls, value: datetime) -> datetime:
        return StudentRead.timestamp_as_utc(value)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    questionnaire_id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_as_utc(cls, value: datetime) -> datetime:
        return StudentRead.timestamp_as_utc(value)


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class ChatResponse(BaseModel):
    conversation_id: int
    student_message: MessageRead
    assistant_message: MessageRead


class ChatErrorDetail(BaseModel):
    code: str
    message: str
    conversation_id: int
    student_message_id: int


class ChatErrorResponse(BaseModel):
    detail: ChatErrorDetail
