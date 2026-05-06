"""Finding schema. Severity and Confidence are independent axes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Phrases that turn `recommended_investigation` into an instruction rather than
# a question. The PRD's hard rule: every recommendation is a question for the
# human, never a directive. Validators reject these prefixes.
_INSTRUCTION_PREFIXES: tuple[str, ...] = (
    "add ",
    "remove ",
    "delete ",
    "rewrite ",
    "refactor ",
    "fix ",
    "update ",
    "change ",
    "implement ",
    "create ",
    "write ",
    "edit ",
    "modify ",
    "replace ",
    "merge ",
    "revert ",
    "apply ",
)


class Severity(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class Confidence(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Finding(BaseModel):
    """A single rule output. Severity and confidence are independent.

    `recommended_investigation` must always be a question for the human, never
    an instruction to take an action — enforced by validator.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    rule_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    severity: Severity
    confidence: Confidence
    knowledge_refs: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_investigation: str = Field(min_length=1)

    @field_validator("rule_id")
    @classmethod
    def _rule_id_is_snake_case(cls, v: str) -> str:
        if not v.replace("_", "").isalnum() or not v.islower():
            raise ValueError(f"rule_id must be lowercase snake_case, got {v!r}")
        return v

    @field_validator("knowledge_refs")
    @classmethod
    def _non_info_findings_must_cite(cls, v: list[str], info: Any) -> list[str]:
        # Only Info findings are allowed to ship without a knowledge_ref. Every
        # other severity must cite at least one corpus doc — that's the
        # "if you can't cite, you can't claim" rule from the PRD.
        severity = info.data.get("severity") if hasattr(info, "data") else None
        if severity is not None and severity != Severity.INFO and not v:
            raise ValueError(
                "non-Info findings must cite at least one knowledge_ref "
                "(if you can't cite, you can't claim)"
            )
        return v

    @field_validator("recommended_investigation")
    @classmethod
    def _is_a_question_not_an_instruction(cls, v: str) -> str:
        stripped = v.strip()
        lower = stripped.lower()
        if lower.startswith(_INSTRUCTION_PREFIXES):
            raise ValueError(
                f"recommended_investigation must be phrased as a question for the "
                f"human, not an instruction to take action. Got: {stripped!r}"
            )
        return stripped
