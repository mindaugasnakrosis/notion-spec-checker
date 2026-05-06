"""On-disk check manifest. Read by `analyse` to know which rules can run."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CollectorState = Literal["ok", "skipped", "failed"]


class CollectorStatus(BaseModel):
    """How one collector fared during `pull`. Failed collectors don't kill the
    run; rules that depend on the missing data emit Info findings instead.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    state: CollectorState
    detail: str | None = None
    artefact_path: str | None = None


class CheckManifest(BaseModel):
    """Top-level manifest for one check run, written to <snapshot>/manifest.yaml."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    check_id: str = Field(min_length=1)
    created_at: datetime
    spec_check_version: str = Field(min_length=1)

    branch: str = Field(min_length=1)
    base_ref: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)

    resolved_spec_id: str | None = None
    resolved_spec_url: str | None = None
    resolution_method: str | None = None  # "ticket_key" | "trailer" | "fuzzy" | "override"

    collectors: list[CollectorStatus] = Field(default_factory=list)
