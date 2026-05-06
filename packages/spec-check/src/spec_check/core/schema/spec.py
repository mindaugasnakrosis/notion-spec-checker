"""Parsed Notion spec schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CriterionStyle = Literal["given_when_then", "bullet", "checklist"]


class AmbiguityFlag(BaseModel):
    """A single instance of imprecise language inside a criterion."""

    model_config = ConfigDict(extra="forbid")

    phrase: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class AcceptanceCriterion(BaseModel):
    """One acceptance criterion, parsed out of a Notion page."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    style: CriterionStyle
    observable: bool
    ambiguity_flags: list[AmbiguityFlag] = Field(default_factory=list)
    line_in_source: int | None = None

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if " " in v:
            raise ValueError(f"AcceptanceCriterion.id may not contain spaces, got {v!r}")
        return v


class ParsedSpec(BaseModel):
    """A Notion page parsed into the structure spec-check rules consume."""

    model_config = ConfigDict(extra="forbid")

    notion_page_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    last_edited_time: datetime
    has_ac_section: bool
    criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    other_blocks: dict[str, Any] = Field(default_factory=dict)
