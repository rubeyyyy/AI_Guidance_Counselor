"""The model supplies plan content; identity and progress belong to the server."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=1800)]


class PlannedStep(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    horizon: Literal['short', 'long']
    title: Annotated[str, Field(min_length=1, max_length=140)]
    action: Text
    why: Text
    evidence: Text
    timing: Annotated[str, Field(min_length=1, max_length=250)]
    weekly_minutes: Annotated[int, Field(strict=True, ge=0, le=10080)]


class GeneratedPathway(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    pace: Text
    adaptations: Annotated[list[Text], Field(min_length=1, max_length=8)]
    steps: Annotated[list[PlannedStep], Field(min_length=4, max_length=12)]

    @model_validator(mode='after')
    def both_horizons(self):
        if {step.horizon for step in self.steps} != {'short', 'long'}:
            raise ValueError('Both short- and long-term steps are required')
        return self
