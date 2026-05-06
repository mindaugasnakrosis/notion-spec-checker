"""Parsed git diff schema."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChangedHunk(BaseModel):
    """One contiguous changed region in a single file."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1)
    start_line: int = Field(ge=0)
    end_line: int = Field(ge=0)
    added_lines: list[str] = Field(default_factory=list)
    removed_lines: list[str] = Field(default_factory=list)
    is_test_file: bool = False

    @model_validator(mode="after")
    def _line_ordering(self) -> ChangedHunk:
        if self.end_line < self.start_line:
            raise ValueError(
                f"end_line ({self.end_line}) must be >= start_line ({self.start_line}) "
                f"in {self.file}"
            )
        return self


class ParsedDiff(BaseModel):
    """A git diff parsed into hunks. base_ref → head_sha on a named branch."""

    model_config = ConfigDict(extra="forbid")

    base_ref: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    files_changed: int = Field(ge=0)
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    hunks: list[ChangedHunk] = Field(default_factory=list)
    test_files_touched: list[str] = Field(default_factory=list)

    @field_validator("head_sha")
    @classmethod
    def _sha_shape(cls, v: str) -> str:
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError(f"head_sha must be hex, got {v!r}")
        if len(v) < 7:
            raise ValueError(f"head_sha must be at least 7 chars, got {v!r}")
        return v.lower()
