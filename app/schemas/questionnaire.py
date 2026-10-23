from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator

AnswerValue = StrictStr | StrictInt | StrictFloat | list[StrictStr] | None


class QuestionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    key: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1)
    response_type: Literal["text", "number", "single-choice", "multiple-choice"]
    required: bool
    display_order: int = Field(ge=0)
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_options(self):
        choice = self.response_type in ("single-choice", "multiple-choice")
        if choice != bool(self.options):
            raise ValueError("Choice questions need options; text and number questions have none")
        if len(set(self.options)) != len(self.options) or any(not s.strip() for s in self.options):
            raise ValueError("Options must be nonblank and unique")
        return self


class QuestionRead(QuestionDefinition):
    id: int
    required_when: dict[str, str] | None = None


class QuestionnaireDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    is_sample: bool
    questions: list[QuestionDefinition]

    @model_validator(mode="after")
    def unique_keys(self):
        if len({q.key for q in self.questions}) != len(self.questions):
            raise ValueError("Question keys must be unique")
        return self


class AnswerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: AnswerValue


class AnswerRead(AnswerWrite):
    model_config = ConfigDict(extra="forbid", from_attributes=True, allow_inf_nan=False)
    question_id: int


class Progress(BaseModel):
    total_questions: int
    answered_questions: int
    required_questions: int
    answered_required_questions: int
    completion_percent: float
    is_complete: bool


class ProfileField(BaseModel):
    key: str
    question_id: int
    value: AnswerValue


class StudentProfile(BaseModel):
    student_id: int
    display_name: str | None
    questionnaire_id: str
    is_sample: bool
    fields: list[ProfileField]
    progress: Progress
