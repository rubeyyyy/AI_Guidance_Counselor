"""Typed answers to the supplied Google Form; choice labels match the form."""

from typing import Annotated, Literal, Self, TypeVar

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StrictBool,
    StringConstraints, model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


OptionalText = Annotated[Text | None, BeforeValidator(blank_to_none)]
T = TypeVar("T")


def unique_selections(values: list[T]) -> list[T]:
    if len(values) != len(set(values)):
        raise ValueError("Select each option only once")
    return values


Selections = Annotated[list[T], Field(min_length=1), AfterValidator(unique_selections)]
AwarenessAnswer = Literal["Yes", "No", "Somewhat"]
ShortTermTimeline = Literal[
    "3-6 Month", "6 month - 1 Year", "1-2 Years", "More than 2 Years"
]
LongTermTimeline = Literal["6 month - 1 Year", "1-3 Years", "More than 3 Years"]
Confidence = Literal["Very confident", "Somewhat confident", "Not sure yet"]
Motivator = Literal[
    "Financial stability", "Passion/interest", "Helping people", "Family expectations", "Other"
]
SoftSkill = Literal[
    "Communication", "Problem-Solving", "Adaptability", "Teamwork", "Time Management",
    "Leadership", "Critical Thinking", "Emotional Intelligence (EQ)", "Creativity",
    "Strong Work ethic",
]
Proficiency = Literal["Basic", "Intermediate", "Advanced"]
SocioeconomicFactor = Literal[
    "Low Income", "Lower-middle income", "Middle income", "Upper-Middle Income",
    "Upper Income", "Small Business", "First Generation College-Bound", "Part time worker",
    "Need to help care for family",
]
Obstacle = Literal[
    "Lack of information", "Financial limitations", "Lack of mentorship",
    "Academic challenges", "Time constraints", "Family responsibilities", "Not sure yet",
    "Other",
]
LearningPreference = Literal["Video", "Reading", "Hands-on", "Mentorship"]


class AnswerSection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BasicInformation(AnswerSection):
    name: Text
    age: Annotated[int, Field(strict=True, gt=0)]
    grade: Text
    city: Text
    current_program: Text
    # The questionnaire does not specify a GPA scale (weighted GPAs may exceed 4).
    gpa: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]


class CareerGoals(AnswerSection):
    short_term_goal: Text
    short_term_timeline: ShortTermTimeline
    long_term_aspirations: Text
    long_term_timeline: LongTermTimeline
    confidence: Confidence


class CareerAwareness(AnswerSection):
    knows_tutoring_resources: AwarenessAnswer
    knows_how_to_find_internship: AwarenessAnswer
    knows_job_training_resources: AwarenessAnswer
    has_talked_to_career_adult: AwarenessAnswer
    knows_required_education: AwarenessAnswer


class Motivation(AnswerSection):
    career_interest_reason: Text
    primary_motivator: Motivator
    other_motivator: OptionalText = None

    @model_validator(mode="after")
    def validate_other(self) -> Self:
        if (self.primary_motivator == "Other") != (self.other_motivator is not None):
            raise ValueError("other_motivator is required only when primary_motivator is Other")
        return self


class TechnicalSkill(AnswerSection):
    name: Text
    proficiency: Proficiency | None = None


class Skills(AnswerSection):
    soft_skills: Selections[SoftSkill]
    technical_skills: list[TechnicalSkill] | None = None
    # Retain free-text input when importing the original form; never guess its meaning.
    technical_skills_raw: OptionalText = None


class Experience(AnswerSection):
    related_experiences: OptionalText = None
    certifications: OptionalText = None
    clubs_competitions_projects: OptionalText = None


class SupportResources(AnswerSection):
    socioeconomic_factors: Selections[SocioeconomicFactor]
    has_personal_laptop: StrictBool
    has_reliable_internet: StrictBool
    biggest_obstacle: Obstacle
    other_obstacle: OptionalText = None
    weekly_learning_hours: Annotated[
        float, Field(strict=True, ge=0, le=168, allow_inf_nan=False)
    ]
    learning_preferences: Selections[LearningPreference]

    @model_validator(mode="after")
    def validate_other(self) -> Self:
        if (self.biggest_obstacle == "Other") != (self.other_obstacle is not None):
            raise ValueError("other_obstacle is required only when biggest_obstacle is Other")
        return self


class Assessment(AnswerSection):
    basic_information: BasicInformation
    career_goals: CareerGoals
    career_awareness: CareerAwareness
    motivation: Motivation
    skills: Skills
    experience: Experience | None = None
    support_resources: SupportResources
